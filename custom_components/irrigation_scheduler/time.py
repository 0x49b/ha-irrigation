"""Per-weekday watering window (from / to)."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import IrrigationConfigEntry
from .const import WEEKDAYS
from .controller import IrrigationController
from .entity import IrrigationEntity

BOUNDS = ("start", "end")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrrigationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        WindowTime(entry.runtime_data, day, index)
        for day in WEEKDAYS
        for index in range(len(BOUNDS))
    )


class WindowTime(IrrigationEntity, TimeEntity, RestoreEntity):
    """Start or end of the watering window for one weekday."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller: IrrigationController, day: str, index: int) -> None:
        super().__init__(controller, f"window_{BOUNDS[index]}_{day}")
        self._day = day
        self._index = index
        self._attr_icon = "mdi:clock-start" if index == 0 else "mdi:clock-end"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and (
            value := dt_util.parse_time(last.state)
        ):
            self.controller.windows[self._day][self._index] = value

    @property
    def native_value(self) -> time:
        return self.controller.windows[self._day][self._index]

    async def async_set_value(self, value: time) -> None:
        self.controller.windows[self._day][self._index] = value
        self.controller.async_schedule_changed()
