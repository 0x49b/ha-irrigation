"""Sensors for Irrigation Scheduler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPrecipitationDepth,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IrrigationConfigEntry
from .const import STATUSES
from .controller import IrrigationController
from .entity import IrrigationEntity


@dataclass(frozen=True, kw_only=True)
class IrrigationSensorDescription(SensorEntityDescription):
    value_fn: Callable[[IrrigationController], datetime | float | str | None]


SENSORS = (
    IrrigationSensorDescription(
        key="status",
        device_class=SensorDeviceClass.ENUM,
        options=STATUSES,
        value_fn=lambda c: c.status,
    ),
    IrrigationSensorDescription(
        key="next_run",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: c.next_run,
    ),
    IrrigationSensorDescription(
        key="last_run",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: c.last_run,
    ),
    IrrigationSensorDescription(
        key="today_duration",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-sand",
        value_fn=lambda c: c.next_run_duration,
    ),
    IrrigationSensorDescription(
        key="rain_forecast",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.rain.amount_mm if c.rain else None,
    ),
    IrrigationSensorDescription(
        key="rain_probability",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        value_fn=lambda c: c.rain.max_probability if c.rain else None,
    ),
)


WATER_SENSORS = (
    IrrigationSensorDescription(
        key="water_last_run",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        value_fn=lambda c: c.last_water_l,
    ),
    IrrigationSensorDescription(
        key="water_cost_total",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda c: c.cost_total,
    ),
    IrrigationSensorDescription(
        key="water_total",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        value_fn=lambda c: c.water_total_l,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrrigationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    controller = entry.runtime_data
    descriptions = SENSORS + (WATER_SENSORS if controller.water_entity else ())
    async_add_entities(IrrigationSensor(controller, d) for d in descriptions)


class IrrigationSensor(IrrigationEntity, SensorEntity):
    entity_description: IrrigationSensorDescription

    def __init__(
        self, controller: IrrigationController, description: IrrigationSensorDescription
    ) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description
        if description.device_class is SensorDeviceClass.MONETARY:
            self._attr_native_unit_of_measurement = controller.currency

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.controller)
