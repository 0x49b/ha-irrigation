"""Measure water used during a run from a volume meter or a flow sensor."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfVolume, UnitOfVolumeFlowRate
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import VolumeConverter, VolumeFlowRateConverter

from .logic import meter_consumption

_LOGGER = logging.getLogger(__name__)

MODE_METER = "meter"
MODE_FLOW = "flow"


class WaterTracker:
    """Tracks the water of the currently running history record.

    Meter sensors (L, m³, gal, ...) are read at start and end. Flow sensors
    (L/min, m³/h, ...) are integrated over time on every state change.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self.hass = hass
        self.entity_id = entity_id
        self._record: dict[str, Any] | None = None
        self._unsub: CALLBACK_TYPE | None = None
        self._last: tuple[datetime, float] | None = None

    def read(self, state: State | None = None) -> tuple[str, float] | None:
        """Return (mode, value) in liters or liters/minute, or None if unusable."""
        state = state or self.hass.states.get(self.entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        unit = state.attributes.get("unit_of_measurement")
        if unit in VolumeConverter.VALID_UNITS:
            return MODE_METER, VolumeConverter.convert(value, unit, UnitOfVolume.LITERS)
        if unit in VolumeFlowRateConverter.VALID_UNITS:
            return MODE_FLOW, VolumeFlowRateConverter.convert(
                value, unit, UnitOfVolumeFlowRate.LITERS_PER_MINUTE
            )
        _LOGGER.warning("%s has unsupported unit %s for water tracking", self.entity_id, unit)
        return None

    @callback
    def start(self, record: dict[str, Any]) -> None:
        """Start (or resume after restart) tracking for `record`."""
        self._record = record
        reading = self.read()
        if reading is None:
            return
        mode, value = reading
        record["water_mode"] = mode
        record.setdefault("water_l", 0.0)
        if mode == MODE_METER:
            record.setdefault("water_start", value)
        else:
            self._last = (dt_util.utcnow(), value)
            self._unsub = async_track_state_change_event(
                self.hass, [self.entity_id], self._on_flow_change
            )

    @callback
    def _on_flow_change(self, event: Event[EventStateChangedData]) -> None:
        reading = self.read(event.data["new_state"])
        now = dt_util.utcnow()
        self._integrate(now)
        # Unusable state: assume no flow until the next valid report.
        self._last = (now, reading[1] if reading and reading[0] == MODE_FLOW else 0.0)

    def _integrate(self, now: datetime) -> None:
        if self._record is None or self._last is None:
            return
        since, rate = self._last
        minutes = max((now - since).total_seconds(), 0) / 60
        self._record["water_l"] = round(self._record["water_l"] + rate * minutes, 2)

    @callback
    def stop(self) -> None:
        """Finish tracking and write the final amount into the record."""
        record = self._record
        if record is not None and record.get("water_mode") == MODE_FLOW:
            self._integrate(dt_util.utcnow())
        elif record is not None and record.get("water_mode") == MODE_METER:
            self.update_meter(record)
        self.cancel()

    @callback
    def update_meter(self, record: dict[str, Any]) -> None:
        """(Re)compute a meter record from the current reading."""
        reading = self.read()
        if reading and reading[0] == MODE_METER and "water_start" in record:
            record["water_l"] = round(meter_consumption(record["water_start"], reading[1]), 2)

    @callback
    def cancel(self) -> None:
        if self._unsub:
            self._unsub()
        self._unsub = None
        self._record = None
        self._last = None
