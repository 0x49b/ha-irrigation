"""Switches: automatic mode, rain check and manual watering."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import IrrigationConfigEntry
from .controller import IrrigationController
from .entity import IrrigationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrrigationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    controller = entry.runtime_data
    async_add_entities(
        [
            FlagSwitch(controller, "automatic", "auto_enabled", "mdi:calendar-clock"),
            FlagSwitch(controller, "rain_check", "rain_check_enabled", "mdi:weather-pouring"),
            WateringSwitch(controller),
        ]
    )


class FlagSwitch(IrrigationEntity, SwitchEntity, RestoreEntity):
    """Switch that toggles a boolean attribute of the controller."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, controller: IrrigationController, key: str, attr: str, icon: str
    ) -> None:
        super().__init__(controller, key)
        self._flag = attr
        self._attr_icon = icon

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if last := await self.async_get_last_state():
            setattr(self.controller, self._flag, last.state != STATE_OFF)

    @property
    def is_on(self) -> bool:
        return getattr(self.controller, self._flag)

    async def async_turn_on(self, **kwargs: Any) -> None:
        setattr(self.controller, self._flag, True)
        self.controller.async_notify()

    async def async_turn_off(self, **kwargs: Any) -> None:
        setattr(self.controller, self._flag, False)
        self.controller.async_notify()


class WateringSwitch(IrrigationEntity, SwitchEntity):
    """Manual start/stop. Uses today's duration, ignores the rain check."""

    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, "watering")

    @property
    def is_on(self) -> bool:
        return self.controller.is_running

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"run_end": self.controller.run_end}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_run(check_rain=False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.async_stop()
