"""Irrigation Scheduler integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import websocket_api
from .const import DOMAIN, PANEL_URL, STATIC_URL
from .controller import IrrigationController

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PANEL_JS = "irrigation-panel.js"

type IrrigationConfigEntry = ConfigEntry[IrrigationController]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    websocket_api.async_register(hass)
    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(frontend_dir), cache_headers=False)]
    )
    # Cache-bust the module on every version bump.
    version = (await hass.async_add_executor_job(
        (frontend_dir / PANEL_JS).stat
    )).st_mtime_ns
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="irrigation-scheduler-panel",
        frontend_url_path=PANEL_URL,
        sidebar_title="Bewässerung",
        sidebar_icon="mdi:sprinkler-variant",
        module_url=f"{STATIC_URL}/{PANEL_JS}?v={version}",
        require_admin=True,
    )
    return True


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
