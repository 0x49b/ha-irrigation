"""Irrigation Scheduler integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .controller import IrrigationController

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

type IrrigationConfigEntry = ConfigEntry[IrrigationController]


async def async_setup_entry(hass: HomeAssistant, entry: IrrigationConfigEntry) -> bool:
    controller = IrrigationController(hass, entry)
    entry.runtime_data = controller
    # Platforms first so restored number/switch states are loaded before scheduling.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await controller.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IrrigationConfigEntry) -> bool:
    await entry.runtime_data.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: IrrigationConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
