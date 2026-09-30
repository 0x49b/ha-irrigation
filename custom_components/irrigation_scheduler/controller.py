"""Irrigation controller: scheduling, rain check and valve control."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
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
    CONF_VALVE_ENTITY,
    CONF_WASTEWATER_ENABLED,
    CONF_WASTEWATER_PRICE,
    CONF_WATER_ENTITY,
    CONF_WATER_PRICE,
    CONF_WEATHER_ENTITY,
    DEFAULT_DURATION_MIN,
    DEFAULT_WASTEWATER_ENABLED,
    DEFAULT_WASTEWATER_PRICE,
    DEFAULT_WATER_PRICE,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    DOMAIN,
    HISTORY_DAYS,
    OPTION_KEYS,
    RAIN_REFRESH_MINUTES,
    RESULT_COMPLETED,
    RESULT_ERROR,
    RESULT_STOPPED,
    SIGNAL_UPDATE,
    SOURCE_AUTO,
    SOURCE_MANUAL,
    STATUS_ERROR,
    STATUS_IDLE,
    STATUS_SKIPPED_NO_DURATION,
    STATUS_SKIPPED_RAIN,
    STATUS_WATERING,
    WEEKDAYS,
)
from .logic import RainAssessment, assess_rain, compute_next_run, water_cost
from .water import WaterTracker

# Meters often report with a delay; re-read this long after the valve closed.
WATER_SETTLE_SECONDS = 90

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1


class IrrigationController:
    """Holds the runtime state of one irrigation zone."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config: dict[str, Any] = {**entry.data, **entry.options}

        self.durations: dict[str, float] = dict.fromkeys(WEEKDAYS, DEFAULT_DURATION_MIN)
        default_window = (
            dt_util.parse_time(DEFAULT_WINDOW_START),
            dt_util.parse_time(DEFAULT_WINDOW_END),
        )
        self.windows: dict[str, list[time]] = {d: list(default_window) for d in WEEKDAYS}
        self.auto_enabled = True
        self.rain_check_enabled = True

        self.status = STATUS_IDLE
        self.next_run: datetime | None = None
        self.next_run_day: str | None = None
        self.last_run: datetime | None = None
        self.run_end: datetime | None = None
        self.rain: RainAssessment | None = None
        self.history: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self.water_total_l = 0.0
        self.last_water_l: float | None = None
        self.cost_total = 0.0
        self.last_cost: float | None = None
        self._water = (
            WaterTracker(hass, water) if (water := self.config.get(CONF_WATER_ENTITY)) else None
        )
        self._unsub_settle: list[CALLBACK_TYPE] = []

        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsub_schedule: CALLBACK_TYPE | None = None
        self._unsub_finish: CALLBACK_TYPE | None = None
        self._unsub_rain: CALLBACK_TYPE | None = None
        self._started = False

    # ---------------------------------------------------------------- props

    @property
    def valve_entity(self) -> str:
        return self.config[CONF_VALVE_ENTITY]

    @property
    def weather_entity(self) -> str:
        return self.config[CONF_WEATHER_ENTITY]

    @property
    def water_entity(self) -> str | None:
        return self._water.entity_id if self._water else None

    @property
    def currency(self) -> str:
        return self.hass.config.currency

    @property
    def price_per_m3(self) -> float:
        """Current total tariff: fresh water plus wastewater if enabled."""
        price = float(self.config.get(CONF_WATER_PRICE, DEFAULT_WATER_PRICE))
        if self.config.get(CONF_WASTEWATER_ENABLED, DEFAULT_WASTEWATER_ENABLED):
            price += float(self.config.get(CONF_WASTEWATER_PRICE, DEFAULT_WASTEWATER_PRICE))
        return price

    @property
    def is_running(self) -> bool:
        return self.run_end is not None

    def duration_for(self, when: datetime) -> float:
        return self.durations[WEEKDAYS[when.weekday()]]

    @property
    def next_run_duration(self) -> float | None:
        return self.durations[self.next_run_day] if self.next_run_day else None

    def as_dict(self) -> dict[str, Any]:
        """Serializable snapshot for the frontend panel."""

        def iso(value: datetime | None) -> str | None:
            return value.isoformat() if value else None

        return {
            "entry_id": self.entry.entry_id,
            "title": self.entry.title,
            "status": self.status,
            "running": self.is_running,
            "run_end": iso(self.run_end),
            "next_run": iso(self.next_run),
            "next_run_day": self.next_run_day,
            "next_run_duration": self.next_run_duration,
            "last_run": iso(self.last_run),
            "auto_enabled": self.auto_enabled,
            "rain_check_enabled": self.rain_check_enabled,
            "rain": (
                {
                    "amount_mm": self.rain.amount_mm,
                    "max_probability": self.rain.max_probability,
                    "skip": self.rain.skip,
                }
                if self.rain
                else None
            ),
            "days": [
                {
                    "day": day,
                    "duration": self.durations[day],
                    "start": self.windows[day][0].strftime("%H:%M"),
                    "end": self.windows[day][1].strftime("%H:%M"),
                }
                for day in WEEKDAYS
            ],
            "options": {key: self.config.get(key) for key in OPTION_KEYS},
            "water_entity": self.water_entity,
            "water_total_l": self.water_total_l if self._water else None,
            "last_water_l": self.last_water_l,
            "currency": self.currency,
            "price_per_m3": self.price_per_m3,
            "cost_total": self.cost_total if self._water else None,
            "last_cost": self.last_cost,
            "history": self.history,
        }

    # ------------------------------------------------------------ listeners

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> Callable[[], None]:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def async_notify(self) -> None:
        for update in list(self._listeners):
            update()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    # ------------------------------------------------------------ lifecycle

    async def async_start(self) -> None:
        """Restore persisted state and start timers."""
        stored = await self._store.async_load() or {}
        if last_run := stored.get("last_run"):
            self.last_run = dt_util.parse_datetime(last_run)
        self.history = stored.get("history") or []
        self.water_total_l = stored.get("water_total_l") or 0.0
        self.last_water_l = stored.get("last_water_l")
        self.cost_total = stored.get("cost_total") or 0.0
        self.last_cost = stored.get("last_cost")
        if self.history and self.history[-1].get("end") is None:
            self._current = self.history[-1]
            if self._water:
                self._water.start(self._current)
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
                if self._current:
                    self._close_history(end or dt_util.utcnow(), RESULT_COMPLETED)
                await self._async_save()

        self._started = True
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
        for unsub in self._unsub_settle:
            unsub()
        self._unsub_settle.clear()
        if self._water:
            self._water.cancel()
        self._started = False

    # ------------------------------------------------------------- schedule

    @callback
    def async_schedule_changed(self) -> None:
        """Recompute the next run after a duration or window change."""
        if self._started:
            self._schedule_next()
        else:
            self.async_notify()

    @callback
    def _schedule_next(self) -> None:
        if self._unsub_schedule:
            self._unsub_schedule()
            self._unsub_schedule = None
        # Days without a duration get no slots at all.
        windows = {
            i: tuple(self.windows[day])
            for i, day in enumerate(WEEKDAYS)
            if self.durations[day] > 0
        }
        result = compute_next_run(
            dt_util.now(), windows, float(self.config[CONF_INTERVAL_HOURS])
        )
        if result is None:
            self.next_run = self.next_run_day = None
        else:
            self.next_run, weekday = result
            self.next_run_day = WEEKDAYS[weekday]
            self._unsub_schedule = async_track_point_in_time(
                self.hass, self._async_scheduled_run, self.next_run
            )
        self.async_notify()

    async def _async_scheduled_run(self, _now: datetime) -> None:
        self._unsub_schedule = None
        try:
            if self.auto_enabled and self.next_run_day:
                await self.async_run(
                    duration_min=self.durations[self.next_run_day],
                    check_rain=self.rain_check_enabled,
                    source=SOURCE_AUTO,
                )
        finally:
            self._schedule_next()

    # ------------------------------------------------------------------ run

    async def async_run(
        self,
        duration_min: float | None = None,
        check_rain: bool = True,
        source: str = SOURCE_MANUAL,
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
            self._add_history(now, source, STATUS_SKIPPED_NO_DURATION, 0, end=now)
            await self._async_save()
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
                self._add_history(now, source, STATUS_SKIPPED_RAIN, duration_min, end=now)
                await self._async_save()
                self.async_notify()
                return

        try:
            await self._async_set_valve(True)
        except HomeAssistantError:
            _LOGGER.exception("Could not open valve %s", self.valve_entity)
            self.status = STATUS_ERROR
            self._add_history(now, source, RESULT_ERROR, duration_min, end=now)
            await self._async_save()
            self.async_notify()
            return

        self._current = self._add_history(now, source, None, duration_min)
        if self._water:
            # Tariff at run time; later price changes don't touch this run.
            self._current["price_m3"] = self.price_per_m3
            self._water.start(self._current)
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
        await self._async_finish(None, RESULT_STOPPED)

    async def _async_finish(
        self, _now: datetime | None, result: str = RESULT_COMPLETED
    ) -> None:
        self._unsub_finish = None
        try:
            await self._async_set_valve(False)
            self.status = STATUS_IDLE
        except HomeAssistantError:
            _LOGGER.exception("Could not close valve %s", self.valve_entity)
            self.status = STATUS_ERROR
            result = RESULT_ERROR
        if self._current:
            self._close_history(dt_util.now(), result)
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

    # -------------------------------------------------------------- history

    def _add_history(
        self,
        start: datetime,
        source: str,
        result: str | None,
        planned_min: float,
        end: datetime | None = None,
    ) -> dict[str, Any]:
        entry = {
            "start": start.isoformat(),
            "end": end.isoformat() if end else None,
            "planned_min": planned_min,
            "actual_min": 0 if end else None,
            "source": source,
            "result": result,
            "rain_mm": self.rain.amount_mm if self.rain else None,
            "rain_probability": self.rain.max_probability if self.rain else None,
        }
        self.history.append(entry)
        cutoff = dt_util.now() - timedelta(days=HISTORY_DAYS)
        self.history = [
            h for h in self.history if dt_util.parse_datetime(h["start"]) >= cutoff
        ]
        return entry

    def _close_history(self, end: datetime, result: str) -> None:
        entry = self._current
        self._current = None
        if entry is None:
            return
        start = dt_util.parse_datetime(entry["start"])
        entry["end"] = end.isoformat()
        entry["result"] = result
        entry["actual_min"] = round(max((end - start).total_seconds(), 0) / 60, 1)
        if self._water:
            self._water.stop()
            self._book_water(entry)
            if "water_start" in entry:
                self._schedule_meter_settle(entry)

    def _book_water(self, entry: dict[str, Any]) -> None:
        """Add the (possibly corrected) amount of `entry` to the totals."""
        if (water := entry.get("water_l")) is None:
            return
        self.water_total_l = round(
            self.water_total_l + water - entry.get("water_booked_l", 0.0), 2
        )
        entry["water_booked_l"] = water
        self.last_water_l = water
        if (price := entry.get("price_m3")) is not None:
            cost = water_cost(water, price)
            self.cost_total = round(self.cost_total + cost - entry.get("cost", 0.0), 2)
            entry["cost"] = cost
            self.last_cost = cost

    async def async_recalculate_costs(self) -> int:
        """Price finished runs that have water but no cost with the current tariff."""
        price = self.price_per_m3
        count = 0
        for entry in self.history:
            if entry.get("end") is None or entry.get("water_l") is None or "cost" in entry:
                continue
            entry["price_m3"] = price
            entry["cost"] = water_cost(entry["water_l"], price)
            self.cost_total = round(self.cost_total + entry["cost"], 2)
            count += 1
        if count:
            await self._async_save()
            self.async_notify()
        return count

    def _schedule_meter_settle(self, entry: dict[str, Any]) -> None:
        async def _settle(_now: datetime) -> None:
            self._unsub_settle.remove(unsub)
            if self._water:
                self._water.update_meter(entry)
                self._book_water(entry)
                await self._async_save()
                self.async_notify()

        unsub = async_call_later(self.hass, WATER_SETTLE_SECONDS, _settle)
        self._unsub_settle.append(unsub)

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "last_run": self.last_run.isoformat() if self.last_run else None,
                "run_end": self.run_end.isoformat() if self.run_end else None,
                "history": self.history,
                "water_total_l": self.water_total_l,
                "last_water_l": self.last_water_l,
                "cost_total": self.cost_total,
                "last_cost": self.last_cost,
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
