"""Config and options flow for Irrigation Scheduler."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .const import (
    CONF_INTERVAL_HOURS,
    CONF_LOOKAHEAD_HOURS,
    CONF_MODE,
    CONF_MOISTURE_SENSORS,
    CONF_MOISTURE_THRESHOLD,
    CONF_NEXT_RAIN_MINUTES,
    CONF_NEXT_RAIN_MM,
    CONF_NEXT_RAIN_PROBABILITY,
    CONF_PAST_RAIN_MINUTES,
    CONF_POSTPONE_MINUTES,
    CONF_RAIN_PROBABILITY,
    CONF_RAIN_SENSOR,
    CONF_RAIN_THRESHOLD_MM,
    CONF_VALVE_ENTITY,
    CONF_WASTEWATER_ENABLED,
    CONF_WASTEWATER_PRICE,
    CONF_WATER_ENTITY,
    CONF_WATER_PRICE,
    CONF_WEATHER_ENTITY,
    DEFAULT_INTERVAL_HOURS,
    DEFAULT_LOOKAHEAD_HOURS,
    DEFAULT_NAME,
    DEFAULT_RAIN_PROBABILITY,
    DEFAULT_RAIN_THRESHOLD_MM,
    DEFAULT_WASTEWATER_ENABLED,
    DEFAULT_WASTEWATER_PRICE,
    DEFAULT_WATER_PRICE,
    DOMAIN,
    MODE_DYNAMIC,
    MODE_STATIC,
    MODES,
    OPTION_DEFAULTS,
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
        # Optional: volume meter (L, m³) or flow sensor (L/min, m³/h).
        vol.Optional(
            CONF_WATER_ENTITY,
            description={"suggested_value": defaults.get(CONF_WATER_ENTITY)},
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        # Tariffs per m³ in the Home Assistant currency.
        vol.Required(CONF_WATER_PRICE, default=defaults.get(CONF_WATER_PRICE, DEFAULT_WATER_PRICE)):
            _number(0, 100, 0.01, "/m³"),
        vol.Required(
            CONF_WASTEWATER_PRICE, default=defaults.get(CONF_WASTEWATER_PRICE, DEFAULT_WASTEWATER_PRICE)
        ):
            _number(0, 100, 0.01, "/m³"),
        vol.Required(
            CONF_WASTEWATER_ENABLED, default=defaults.get(CONF_WASTEWATER_ENABLED, DEFAULT_WASTEWATER_ENABLED)
        ):
            selector.BooleanSelector(),
    }


def _static_schema(defaults: dict[str, Any]) -> dict[vol.Marker, Any]:
    """Forecast window check of the static mode."""
    return {
        vol.Required(
            CONF_RAIN_THRESHOLD_MM, default=defaults.get(CONF_RAIN_THRESHOLD_MM, DEFAULT_RAIN_THRESHOLD_MM)
        ):
            _number(0, 100, 0.1, "mm"),
        vol.Required(
            CONF_RAIN_PROBABILITY, default=defaults.get(CONF_RAIN_PROBABILITY, DEFAULT_RAIN_PROBABILITY)
        ):
            _number(0, 100, 1, "%"),
        vol.Required(
            CONF_LOOKAHEAD_HOURS, default=defaults.get(CONF_LOOKAHEAD_HOURS, DEFAULT_LOOKAHEAD_HOURS)
        ):
            _number(1, 72, 1, "h"),
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
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                **_settings_schema({}),
                **_static_schema({}),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IrrigationOptionsFlow()


def _mode_schema(defaults: dict[str, Any]) -> dict[vol.Marker, Any]:
    return {
        vol.Required(CONF_MODE, default=defaults.get(CONF_MODE) or MODE_STATIC):
            selector.SelectSelector(
                selector.SelectSelectorConfig(options=list(MODES), translation_key=CONF_MODE)
            ),
    }


def _dynamic_schema(defaults: dict[str, Any]) -> dict[vol.Marker, Any]:
    def get(key: str) -> Any:
        value = defaults.get(key)
        return OPTION_DEFAULTS[key] if value is None else value

    return {
        vol.Optional(CONF_RAIN_SENSOR, description={"suggested_value": defaults.get(CONF_RAIN_SENSOR)}):
            selector.EntitySelector(selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"])),
        vol.Required(CONF_PAST_RAIN_MINUTES, default=get(CONF_PAST_RAIN_MINUTES)): _number(5, 360, 5, "min"),
        vol.Required(
            CONF_NEXT_RAIN_MINUTES, default=get(CONF_NEXT_RAIN_MINUTES)
        ): _number(15, 360, 15, "min"),
        vol.Required(CONF_NEXT_RAIN_MM, default=get(CONF_NEXT_RAIN_MM)): _number(0, 100, 0.1, "mm"),
        vol.Required(
            CONF_NEXT_RAIN_PROBABILITY, default=get(CONF_NEXT_RAIN_PROBABILITY)
        ): _number(0, 100, 1, "%"),
        vol.Required(CONF_POSTPONE_MINUTES, default=get(CONF_POSTPONE_MINUTES)): _number(15, 360, 15, "min"),
        vol.Optional(CONF_MOISTURE_SENSORS, default=get(CONF_MOISTURE_SENSORS)):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
        vol.Required(CONF_MOISTURE_THRESHOLD, default=get(CONF_MOISTURE_THRESHOLD)): _number(0, 100, 1, "%"),
    }


class IrrigationOptionsFlow(OptionsFlow):
    """Step 1: common settings and mode. Step 2: settings of the chosen mode.

    Settings of the other mode are kept as they are, so switching back restores them.
    """

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            # Explicit None so a cleared field overrides a value from entry.data.
            user_input.setdefault(CONF_WATER_ENTITY, None)
            self._options = {**current, **user_input}
            if user_input[CONF_MODE] == MODE_DYNAMIC:
                return await self.async_step_dynamic()
            return await self.async_step_static()
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({**_mode_schema(current), **_settings_schema(current)}),
        )

    async def async_step_static(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self._options, **user_input})
        return self.async_show_form(
            step_id="static", data_schema=vol.Schema(_static_schema(self._options))
        )

    async def async_step_dynamic(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input.setdefault(CONF_RAIN_SENSOR, None)
            return self.async_create_entry(data={**self._options, **user_input})
        return self.async_show_form(
            step_id="dynamic", data_schema=vol.Schema(_dynamic_schema(self._options))
        )
