"""Binary sensor: rain expected within the lookahead window."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IrrigationConfigEntry
from .controller import IrrigationController
from .entity import IrrigationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrrigationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([RainExpectedBinarySensor(entry.runtime_data)])


class RainExpectedBinarySensor(IrrigationEntity, BinarySensorEntity):
    _attr_icon = "mdi:weather-pouring"

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, "rain_expected")

    @property
    def available(self) -> bool:
        return self.controller.rain is not None

    @property
    def is_on(self) -> bool | None:
        return self.controller.rain.skip if self.controller.rain else None
