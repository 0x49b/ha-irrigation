"""Config and options flow for Irrigation Scheduler."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_INTERVAL_HOURS,
    CONF_LOOKAHEAD_HOURS,
    CONF_RAIN_PROBABILITY,
    CONF_RAIN_THRESHOLD_MM,
    CONF_VALVE_ENTITY,
    CONF_WATER_ENTITY,
    CONF_WEATHER_ENTITY,
    DEFAULT_INTERVAL_HOURS,
    DEFAULT_LOOKAHEAD_HOURS,
    DEFAULT_NAME,
    DEFAULT_RAIN_PROBABILITY,
    DEFAULT_RAIN_THRESHOLD_MM,
    DOMAIN,
)


def _number(min_: float, max_: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_, max=max_, step=step, unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _settings_schema(defaults: dict[str, Any]) -> dict[vol.Marker, Any]:
    return {
        vol.Required(CONF_VALVE_ENTITY, default=defaults.get(CONF_VALVE_ENTITY, vol.UNDEFINED)):
            selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["switch", "valve", "input_boolean"])
            ),
        vol.Required(CONF_WEATHER_ENTITY, default=defaults.get(CONF_WEATHER_ENTITY, vol.UNDEFINED)):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
        vol.Required(CONF_INTERVAL_HOURS, default=defaults.get(CONF_INTERVAL_HOURS, DEFAULT_INTERVAL_HOURS)):
            _number(1, 24, 1, "h"),
        vol.Required(CONF_RAIN_THRESHOLD_MM, default=defaults.get(CONF_RAIN_THRESHOLD_MM, DEFAULT_RAIN_THRESHOLD_MM)):
            _number(0, 100, 0.1, "mm"),
        vol.Required(CONF_RAIN_PROBABILITY, default=defaults.get(CONF_RAIN_PROBABILITY, DEFAULT_RAIN_PROBABILITY)):
            _number(0, 100, 1, "%"),
        vol.Required(CONF_LOOKAHEAD_HOURS, default=defaults.get(CONF_LOOKAHEAD_HOURS, DEFAULT_LOOKAHEAD_HOURS)):
            _number(1, 72, 1, "h"),
        # Optional: volume meter (L, m³) or flow sensor (L/min, m³/h).
        vol.Optional(
            CONF_WATER_ENTITY,
            description={"suggested_value": defaults.get(CONF_WATER_ENTITY)},
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
    }


class IrrigationConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_VALVE_ENTITY])
            self._abort_if_unique_id_configured()
            name = user_input.pop(CONF_NAME)
            return self.async_create_entry(title=name, data=user_input)

        schema = vol.Schema(
            {vol.Required(CONF_NAME, default=DEFAULT_NAME): str, **_settings_schema({})}
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IrrigationOptionsFlow()


class IrrigationOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # Explicit None so a cleared field overrides a value from entry.data.
            user_input.setdefault(CONF_WATER_ENTITY, None)
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(_settings_schema(current))
        )
