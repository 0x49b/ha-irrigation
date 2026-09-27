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
from homeassistant.const import PERCENTAGE, UnitOfPrecipitationDepth, UnitOfTime
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
        value_fn=lambda c: c.duration_for(c.next_run) if c.next_run else None,
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrrigationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(IrrigationSensor(entry.runtime_data, d) for d in SENSORS)


class IrrigationSensor(IrrigationEntity, SensorEntity):
    entity_description: IrrigationSensorDescription

    def __init__(
        self, controller: IrrigationController, description: IrrigationSensorDescription
    ) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.controller)
