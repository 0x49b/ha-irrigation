"""Websocket API used by the sidebar panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect

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
    DOMAIN,
    MAX_DURATION_MIN,
    SIGNAL_UPDATE,
    WEEKDAYS,
)
from .controller import IrrigationController

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_VALVE_ENTITY): cv.entity_domain(["switch", "valve", "input_boolean"]),
        vol.Optional(CONF_WEATHER_ENTITY): cv.entity_domain("weather"),
        vol.Optional(CONF_INTERVAL_HOURS): vol.All(vol.Coerce(float), vol.Range(min=1, max=24)),
        vol.Optional(CONF_RAIN_THRESHOLD_MM): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional(CONF_RAIN_PROBABILITY): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional(CONF_LOOKAHEAD_HOURS): vol.All(vol.Coerce(float), vol.Range(min=1, max=72)),
        vol.Optional(CONF_WATER_ENTITY): vol.Any(None, "", cv.entity_domain("sensor")),
        vol.Optional(CONF_WATER_PRICE): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional(CONF_WASTEWATER_PRICE): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional(CONF_WASTEWATER_ENABLED): bool,
    }
)

_TIME = vol.All(cv.string, cv.time)


@callback
def async_register(hass: HomeAssistant) -> None:
    for command in (
        ws_subscribe,
        ws_set_day,
        ws_set_flags,
        ws_update_options,
        ws_run,
        ws_stop,
        ws_recalculate_costs,
    ):
        websocket_api.async_register_command(hass, command)


def _controllers(hass: HomeAssistant) -> list[IrrigationController]:
    return [
        entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


def _get_controller(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> IrrigationController | None:
    for controller in _controllers(hass):
        if controller.entry.entry_id == msg["entry_id"]:
            return controller
    connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Zone not found")
    return None


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Push a snapshot of all zones on every change (survives entry reloads)."""

    @callback
    def send_snapshot() -> None:
        connection.send_message(
            websocket_api.event_message(
                msg["id"], {"zones": [c.as_dict() for c in _controllers(hass)]}
            )
        )

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_UPDATE, send_snapshot
    )
    connection.send_result(msg["id"])
    send_snapshot()


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_day",
        vol.Required("entry_id"): str,
        vol.Required("day"): vol.In(WEEKDAYS),
        vol.Optional("duration"): vol.All(vol.Coerce(float), vol.Range(min=0, max=MAX_DURATION_MIN)),
        vol.Optional("start"): _TIME,
        vol.Optional("end"): _TIME,
    }
)
@websocket_api.require_admin
@callback
def ws_set_day(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if not (controller := _get_controller(hass, connection, msg)):
        return
    day = msg["day"]
    if "duration" in msg:
        controller.durations[day] = msg["duration"]
    if "start" in msg:
        controller.windows[day][0] = msg["start"]
    if "end" in msg:
        controller.windows[day][1] = msg["end"]
    controller.async_schedule_changed()
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_flags",
        vol.Required("entry_id"): str,
        vol.Optional("auto_enabled"): bool,
        vol.Optional("rain_check_enabled"): bool,
    }
)
@websocket_api.require_admin
@callback
def ws_set_flags(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if not (controller := _get_controller(hass, connection, msg)):
        return
    for flag in ("auto_enabled", "rain_check_enabled"):
        if flag in msg:
            setattr(controller, flag, msg[flag])
    controller.async_notify()
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/update_options",
        vol.Required("entry_id"): str,
        vol.Required("options"): OPTIONS_SCHEMA,
    }
)
@websocket_api.require_admin
@callback
def ws_update_options(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Store new options; the entry's update listener reloads it."""
    if not (controller := _get_controller(hass, connection, msg)):
        return
    entry = controller.entry
    options = {**entry.data, **entry.options, **msg["options"]}
    if CONF_WATER_ENTITY in options:
        options[CONF_WATER_ENTITY] = options[CONF_WATER_ENTITY] or None
    hass.config_entries.async_update_entry(entry, options=options)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/run",
        vol.Required("entry_id"): str,
        vol.Optional("duration"): vol.All(vol.Coerce(float), vol.Range(min=1, max=MAX_DURATION_MIN)),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_run(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if not (controller := _get_controller(hass, connection, msg)):
        return
    await controller.async_run(duration_min=msg.get("duration"), check_rain=False)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/stop", vol.Required("entry_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_stop(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if not (controller := _get_controller(hass, connection, msg)):
        return
    await controller.async_stop()
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/recalculate_costs", vol.Required("entry_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_recalculate_costs(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if not (controller := _get_controller(hass, connection, msg)):
        return
    count = await controller.async_recalculate_costs()
    connection.send_result(msg["id"], {"count": count})
