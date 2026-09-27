"""Irrigation controller: scheduling, rain check and valve control."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_time,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_INTERVAL_HOURS,
    CONF_LOOKAHEAD_HOURS,
    CONF_RAIN_PROBABILITY,
    CONF_RAIN_THRESHOLD_MM,
    CONF_START_TIME,
    CONF_VALVE_ENTITY,
    CONF_WEATHER_ENTITY,
    DEFAULT_DURATION_MIN,
    DOMAIN,
    RAIN_REFRESH_MINUTES,
    STATUS_ERROR,
    STATUS_IDLE,
    STATUS_SKIPPED_NO_DURATION,
    STATUS_SKIPPED_RAIN,
    STATUS_WATERING,
    WEEKDAYS,
)
from .logic import RainAssessment, assess_rain, compute_next_run

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1


class IrrigationController:
    """Holds the runtime state of one irrigation zone."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config: dict[str, Any] = {**entry.data, **entry.options}

        self.durations: dict[str, float] = dict.fromkeys(WEEKDAYS, DEFAULT_DURATION_MIN)
        self.auto_enabled = True
        self.rain_check_enabled = True

        self.status = STATUS_IDLE
        self.next_run: datetime | None = None
        self.last_run: datetime | None = None
        self.run_end: datetime | None = None
        self.rain: RainAssessment | None = None

        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsub_schedule: CALLBACK_TYPE | None = None
        self._unsub_finish: CALLBACK_TYPE | None = None
        self._unsub_rain: CALLBACK_TYPE | None = None

    # ---------------------------------------------------------------- props

    @property
    def valve_entity(self) -> str:
        return self.config[CONF_VALVE_ENTITY]

    @property
    def weather_entity(self) -> str:
        return self.config[CONF_WEATHER_ENTITY]

    @property
    def is_running(self) -> bool:
        return self.run_end is not None

    def duration_for(self, when: datetime) -> float:
        return self.durations[WEEKDAYS[when.weekday()]]

    # ------------------------------------------------------------ listeners

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> Callable[[], None]:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def async_notify(self) -> None:
        for update in list(self._listeners):
            update()

    # ------------------------------------------------------------ lifecycle

    async def async_start(self) -> None:
        """Restore persisted state and start timers."""
        stored = await self._store.async_load() or {}
        if last_run := stored.get("last_run"):
            self.last_run = dt_util.parse_datetime(last_run)
        if run_end := stored.get("run_end"):
            end = dt_util.parse_datetime(run_end)
            if end and end > dt_util.utcnow():
                # HA restarted during a run: keep the valve open until the planned end.
                self.run_end = end
                self.status = STATUS_WATERING
                self._unsub_finish = async_track_point_in_time(
                    self.hass, self._async_finish, end
                )
            else:
                # Run should have ended while HA was down.
                await self._async_set_valve(False)
                await self._async_save()

        self._schedule_next()
        self._unsub_rain = async_track_time_interval(
            self.hass,
            self._async_refresh_rain_job,
            timedelta(minutes=RAIN_REFRESH_MINUTES),
        )
        self.hass.async_create_task(self.async_refresh_rain())

    async def async_shutdown(self) -> None:
        """Cancel timers. Valve state and run_end are kept for restart recovery."""
        for unsub in (self._unsub_schedule, self._unsub_finish, self._unsub_rain):
            if unsub:
                unsub()
        self._unsub_schedule = self._unsub_finish = self._unsub_rain = None

    # ------------------------------------------------------------- schedule

    @callback
    def _schedule_next(self) -> None:
        if self._unsub_schedule:
            self._unsub_schedule()
        start = dt_util.parse_time(self.config[CONF_START_TIME])
        if start is None:
            _LOGGER.error("Invalid start time: %s", self.config[CONF_START_TIME])
            self.next_run = None
            return
        self.next_run = compute_next_run(
            dt_util.now(), start, float(self.config[CONF_INTERVAL_HOURS])
        )
        self._unsub_schedule = async_track_point_in_time(
            self.hass, self._async_scheduled_run, self.next_run
        )
        self.async_notify()

    async def _async_scheduled_run(self, _now: datetime) -> None:
        self._unsub_schedule = None
        try:
            if self.auto_enabled:
                await self.async_run(check_rain=self.rain_check_enabled)
        finally:
            self._schedule_next()

    # ------------------------------------------------------------------ run

    async def async_run(
        self, duration_min: float | None = None, check_rain: bool = True
    ) -> None:
        """Start a run. Uses today's weekday duration unless given explicitly."""
        if self.is_running:
            return
        now = dt_util.now()
        if duration_min is None:
            duration_min = self.duration_for(now)
        if duration_min <= 0:
            _LOGGER.debug("No duration configured for today, skipping")
            self.status = STATUS_SKIPPED_NO_DURATION
            self.async_notify()
            return

        if check_rain:
            await self.async_refresh_rain()
            if self.rain and self.rain.skip:
                _LOGGER.info(
                    "Skipping irrigation: %.1f mm / %s%% rain expected",
                    self.rain.amount_mm,
                    self.rain.max_probability,
                )
                self.status = STATUS_SKIPPED_RAIN
                self.async_notify()
                return

        try:
            await self._async_set_valve(True)
        except HomeAssistantError:
            _LOGGER.exception("Could not open valve %s", self.valve_entity)
            self.status = STATUS_ERROR
            self.async_notify()
            return

        self.last_run = now
        self.run_end = now + timedelta(minutes=duration_min)
        self.status = STATUS_WATERING
        self._unsub_finish = async_call_later(
            self.hass, duration_min * 60, self._async_finish
        )
        await self._async_save()
        self.async_notify()

    async def async_stop(self) -> None:
        """Stop a running irrigation (or just close the valve)."""
        if self._unsub_finish:
            self._unsub_finish()
            self._unsub_finish = None
        await self._async_finish(None)

    async def _async_finish(self, _now: datetime | None) -> None:
        self._unsub_finish = None
        try:
            await self._async_set_valve(False)
            self.status = STATUS_IDLE
        except HomeAssistantError:
            _LOGGER.exception("Could not close valve %s", self.valve_entity)
            self.status = STATUS_ERROR
        self.run_end = None
        await self._async_save()
        self.async_notify()

    async def _async_set_valve(self, on: bool) -> None:
        domain = self.valve_entity.split(".", 1)[0]
        if domain == "valve":
            service = "open_valve" if on else "close_valve"
        else:
            domain, service = "homeassistant", "turn_on" if on else "turn_off"
        await self.hass.services.async_call(
            domain, service, {ATTR_ENTITY_ID: self.valve_entity}, blocking=True
        )

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "last_run": self.last_run.isoformat() if self.last_run else None,
                "run_end": self.run_end.isoformat() if self.run_end else None,
            }
        )

    # ----------------------------------------------------------------- rain

    async def _async_refresh_rain_job(self, _now: datetime) -> None:
        await self.async_refresh_rain()

    async def async_refresh_rain(self) -> None:
        """Fetch forecast from the weather entity and evaluate it."""
        now = dt_util.now()
        for forecast_type, period in (
            ("hourly", timedelta(hours=1)),
            ("daily", timedelta(days=1)),
        ):
            forecast = await self._async_get_forecast(forecast_type)
            if forecast:
                self.rain = assess_rain(
                    forecast,
                    now,
                    float(self.config[CONF_LOOKAHEAD_HOURS]),
                    float(self.config[CONF_RAIN_THRESHOLD_MM]),
                    float(self.config[CONF_RAIN_PROBABILITY]),
                    period,
                )
                self.async_notify()
                return
        _LOGGER.warning("No forecast available from %s", self.weather_entity)
        self.rain = None
        self.async_notify()

    async def _async_get_forecast(self, forecast_type: str) -> list[dict[str, Any]]:
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {ATTR_ENTITY_ID: self.weather_entity, "type": forecast_type},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            _LOGGER.debug("%s forecast not available: %s", forecast_type, err)
            return []
        return (response or {}).get(self.weather_entity, {}).get("forecast") or []
