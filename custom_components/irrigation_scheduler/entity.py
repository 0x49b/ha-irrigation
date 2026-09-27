"""Base entity for Irrigation Scheduler."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import IrrigationController


class IrrigationEntity(Entity):
    """Entity bound to an IrrigationController."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: IrrigationController, key: str) -> None:
        self.controller = controller
        entry = controller.entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Irrigation Scheduler",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.async_add_listener(self.async_write_ha_state))
