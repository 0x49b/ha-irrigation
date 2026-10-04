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
    CONF_MODE,
    CONF_MOISTURE_SENSORS,
    CONF_MOISTURE_THRESHOLD,
    CONF_NEXT_RAIN_MINUTES,
    CONF_NEXT_RAIN_MM,
    CONF_NEXT_RAIN_PROBABILITY,
    CONF_PAST_RAIN_MINUTES,
    CONF_POSTPONE_MINUTES,
    CONF_RAIN_PROBABILITY,
    CONF_RAIN_SENSOR,
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
    MODE_DYNAMIC,
    OPTION_DEFAULTS,
    OPTION_KEYS,
    RAIN_RATE_UNITS,
    RAIN_REFRESH_MINUTES,
    RAINY_CONDITIONS,
    RESULT_COMPLETED,
    RESULT_ERROR,
    RESULT_SKIPPED_MANUAL,
    RESULT_STOPPED,
    SIGNAL_UPDATE,
    SOURCE_AUTO,
    SOURCE_MANUAL,
    STATUS_ERROR,
    STATUS_IDLE,
    STATUS_POSTPONED,
    STATUS_SKIPPED_MOISTURE,
    STATUS_SKIPPED_NO_DURATION,
    STATUS_SKIPPED_RAIN,
    STATUS_WATERING,
    UPCOMING_DAYS,
    WEEKDAYS,
)
from .logic import (
    RainAssessment,
    assess_rain,
    average,
    postpone_target,
    rained_recently,
    upcoming_slots,
    water_cost,
    window_end_for_slot,
)
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
        # Dynamic mode: forecast for the next minutes and result of the last check.
        self.rain_next: RainAssessment | None = None
        self.last_check: dict[str, Any] | None = None
        # (start, weekday, window end) of a run moved by the dynamic rain check.
        self._postponed: tuple[datetime, str, datetime] | None = None
        # Slots the user chose to skip: UTC ISO timestamp -> weekday of its window.
        self.skipped_slots: dict[str, str] = {}
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

    def opt(self, key: str) -> Any:
        """Option value with a default for options older entries don't have."""
        value = self.config.get(key)
        return OPTION_DEFAULTS.get(key) if value is None else value

    @property
    def mode(self) -> str:
        return self.opt(CONF_MODE)

    @property
    def moisture(self) -> float | None:
        """Average of all available soil moisture sensors."""
        return average(_float_state(self.hass, e) for e in self.opt(CONF_MOISTURE_SENSORS))

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
            "options": {key: self.opt(key) for key in OPTION_KEYS},
            "mode": self.mode,
            "rain_next": (
                {
                    "amount_mm": self.rain_next.amount_mm,
                    "max_probability": self.rain_next.max_probability,
                    "skip": self.rain_next.skip,
                }
                if self.rain_next
                else None
            ),
            "moisture": self.moisture,
            "moisture_sensors": [
                {"entity_id": e, "value": _float_state(self.hass, e)}
                for e in self.opt(CONF_MOISTURE_SENSORS)
            ],
            "last_check": self.last_check,
            "postponed": iso(self._postponed[0]) if self._postponed else None,
            "upcoming": [
                {
                    "time": slot.isoformat(),
                    "day": day,
                    "duration": self.durations[day],
                    "skipped": _slot_key(slot) in self.skipped_slots,
                }
                for slot, day in self._upcoming(UPCOMING_DAYS)
            ],
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
        self.last_check = stored.get("last_check")
        self.skipped_slots = stored.get("skipped_slots") or {}
        if postponed := stored.get("postponed"):
            start, day, window_end = postponed
            self._postponed = (
                dt_util.parse_datetime(start), day, dt_util.parse_datetime(window_end)
            )
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
        self._log_passed_skips()
        if self._postponed and self._postponed[0] > dt_util.now():
            self.next_run, self.next_run_day, _ = self._postponed
            self._unsub_schedule = async_track_point_in_time(
                self.hass, self._async_scheduled_run, self.next_run
            )
            self.async_notify()
            return
        self._postponed = None
        result = self._next_regular_slot()
        if result is None:
            self.next_run = self.next_run_day = None
        else:
            self.next_run, self.next_run_day = result
            self._unsub_schedule = async_track_point_in_time(
                self.hass, self._async_scheduled_run, self.next_run
            )
        self.async_notify()

    def _upcoming(self, days: float) -> list[tuple[datetime, str]]:
        # Days without a duration get no slots at all.
        windows = {
            i: tuple(self.windows[day])
            for i, day in enumerate(WEEKDAYS)
            if self.durations[day] > 0
        }
        slots = upcoming_slots(
            dt_util.now(), windows, float(self.config[CONF_INTERVAL_HOURS]), days
        )
        return [(slot, WEEKDAYS[weekday]) for slot, weekday in slots]

    def _next_regular_slot(self) -> tuple[datetime, str] | None:
        """Next slot that the user didn't skip."""
        for slot, day in self._upcoming(UPCOMING_DAYS + 1):
            if _slot_key(slot) not in self.skipped_slots:
                return slot, day
        return None

    async def async_set_skip(self, slot: datetime, skip: bool) -> bool:
        """Skip or un-skip an upcoming slot. Returns False if `slot` isn't one."""
        key = _slot_key(slot)
        day = next(
            (d for s, d in self._upcoming(UPCOMING_DAYS + 1) if _slot_key(s) == key), None
        )
        if day is None:
            return False
        if skip:
            self.skipped_slots[key] = day
        else:
            self.skipped_slots.pop(key, None)
        await self._async_save()
        self._schedule_next()
        return True

    def _log_passed_skips(self) -> None:
        """Move skipped slots that have passed into the history."""
        now = dt_util.utcnow()
        for key in sorted(self.skipped_slots):
            slot = dt_util.parse_datetime(key)
            if slot is None or slot > now:
                continue
            day = self.skipped_slots.pop(key)
            local = dt_util.as_local(slot)
            self._add_history(local, SOURCE_AUTO, RESULT_SKIPPED_MANUAL, self.durations[day], end=local)

    async def _async_scheduled_run(self, _now: datetime) -> None:
        self._unsub_schedule = None
        # Earlier skipped slots go into the history before this run's entry.
        self._log_passed_skips()
        slot, day = self.next_run, self.next_run_day
        postponed, self._postponed = self._postponed, None
        try:
            if not (self.auto_enabled and day and slot):
                return
            if self.mode == MODE_DYNAMIC:
                window_end = (
                    postponed[2] if postponed else window_end_for_slot(slot, *self.windows[day])
                )
                await self._async_dynamic_run(day, window_end)
            else:
                await self.async_run(
                    duration_min=self.durations[day],
                    check_rain=self.rain_check_enabled,
                    source=SOURCE_AUTO,
                )
        finally:
            self._schedule_next()

    # -------------------------------------------------------------- dynamic

    async def _async_dynamic_run(self, day: str, window_end: datetime) -> None:
        """Check soil and rain right before a scheduled run, then run, postpone or skip."""
        duration = self.durations[day]
        now = dt_util.now()
        check = await self._async_dynamic_check(now)
        self.last_check = check

        threshold = float(self.opt(CONF_MOISTURE_THRESHOLD))
        if check["moisture"] is not None and check["moisture"] >= threshold:
            _LOGGER.info("Skipping irrigation: soil moisture %s%% >= %s%%", check["moisture"], threshold)
            self._skip(now, STATUS_SKIPPED_MOISTURE, duration, check)
            await self._async_save()
            self.async_notify()
            return

        if self.rain_check_enabled and (check["past_rain"] or check["next_rain"]):
            next_slot = self._next_regular_slot()
            target = postpone_target(
                now,
                float(self.opt(CONF_POSTPONE_MINUTES)),
                window_end,
                next_slot[0] if next_slot else None,
            )
            if target is not None:
                _LOGGER.info("Rain around the slot, postponing irrigation to %s", target)
                self._postponed = (target, day, window_end)
                self._skip(now, STATUS_POSTPONED, duration, check)
            else:
                _LOGGER.info("Rain around the slot and no time left in the window, skipping")
                self._skip(now, STATUS_SKIPPED_RAIN, duration, check)
            await self._async_save()
            self.async_notify()
            return

        await self.async_run(duration_min=duration, check_rain=False, source=SOURCE_AUTO)

    def _skip(self, now: datetime, status: str, duration: float, check: dict[str, Any]) -> None:
        self.status = status
        entry = self._add_history(now, SOURCE_AUTO, status, duration, end=now)
        entry["check"] = check

    async def _async_dynamic_check(self, now: datetime) -> dict[str, Any]:
        past_minutes = float(self.opt(CONF_PAST_RAIN_MINUTES))
        past_rain, source = await self._async_past_rain(now - timedelta(minutes=past_minutes), now)
        await self.async_refresh_rain()
        return {
            "time": now.isoformat(),
            "moisture": self.moisture,
            "past_rain": past_rain,
            "past_source": source,
            "next_mm": self.rain_next.amount_mm if self.rain_next else None,
            "next_probability": self.rain_next.max_probability if self.rain_next else None,
            "next_rain": bool(self.rain_next and self.rain_next.skip),
        }

    async def _async_past_rain(self, start: datetime, end: datetime) -> tuple[bool, str]:
        """Rain between start and end, from the rain sensor or the weather condition history."""
        entity_id = self.opt(CONF_RAIN_SENSOR) or self.weather_entity
        domain = entity_id.split(".", 1)[0]
        if domain == "binary_sensor":
            kind = "binary"
        elif domain == "weather":
            kind = "condition"
        else:
            state = self.hass.states.get(entity_id)
            unit = state.attributes.get("unit_of_measurement") if state else None
            kind = "rate" if unit in RAIN_RATE_UNITS else "amount"
        values = await self._async_state_history(entity_id, start, end)
        return rained_recently(kind, values, RAINY_CONDITIONS), entity_id

    async def _async_state_history(self, entity_id: str, start: datetime, end: datetime) -> list[str]:
        """States of `entity_id` from `start` (incl. the state at `start`) to now."""
        current = self.hass.states.get(entity_id)
        tail = [current.state] if current else []
        try:
            from homeassistant.components.recorder import get_instance, history

            def _fetch() -> dict[str, list[Any]]:
                return history.state_changes_during_period(
                    self.hass, start, end, entity_id, include_start_time_state=True
                )

            states = await get_instance(self.hass).async_add_executor_job(_fetch)
        except Exception:  # noqa: BLE001 - recorder missing or failing: use current state
            _LOGGER.debug("No recorder history for %s, using current state", entity_id, exc_info=True)
            return tail
        return [s.state for s in states.get(entity_id, [])] + tail

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
                "last_check": self.last_check,
                "skipped_slots": self.skipped_slots,
                "postponed": (
                    [self._postponed[0].isoformat(), self._postponed[1], self._postponed[2].isoformat()]
                    if self._postponed
                    else None
                ),
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
                # The short "next minutes" check needs hourly data.
                self.rain_next = (
                    assess_rain(
                        forecast,
                        now,
                        float(self.opt(CONF_NEXT_RAIN_MINUTES)) / 60,
                        float(self.opt(CONF_NEXT_RAIN_MM)),
                        float(self.opt(CONF_NEXT_RAIN_PROBABILITY)),
                        period,
                    )
                    if forecast_type == "hourly"
                    else None
                )
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
        self.rain = self.rain_next = None
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


def _float_state(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    try:
        return float(state.state) if state else None
    except ValueError:
        return None


def _slot_key(slot: datetime) -> str:
    return dt_util.as_utc(slot).isoformat()
