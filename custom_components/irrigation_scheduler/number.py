"""Per-weekday irrigation duration."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IrrigationConfigEntry
from .const import DEFAULT_DURATION_MIN, MAX_DURATION_MIN, WEEKDAYS
from .controller import IrrigationController
from .entity import IrrigationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrrigationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        WeekdayDurationNumber(entry.runtime_data, day) for day in WEEKDAYS
    )


class WeekdayDurationNumber(IrrigationEntity, RestoreNumber):
    """Watering duration in minutes for one weekday (0 = no watering)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_DURATION_MIN
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-outline"

    def __init__(self, controller: IrrigationController, day: str) -> None:
        super().__init__(controller, f"duration_{day}")
        self._day = day

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        value = DEFAULT_DURATION_MIN
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            value = last.native_value
        self.controller.durations[self._day] = value

    @property
    def native_value(self) -> float:
        return self.controller.durations[self._day]

    async def async_set_native_value(self, value: float) -> None:
        self.controller.durations[self._day] = value
        self.controller.async_schedule_changed()
