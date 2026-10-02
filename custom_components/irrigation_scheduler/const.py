"""Constants for the Irrigation Scheduler integration."""

from __future__ import annotations

DOMAIN = "irrigation_scheduler"

CONF_VALVE_ENTITY = "valve_entity"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_WATER_ENTITY = "water_entity"
CONF_INTERVAL_HOURS = "interval_hours"
CONF_RAIN_THRESHOLD_MM = "rain_threshold_mm"
CONF_RAIN_PROBABILITY = "rain_probability"
CONF_LOOKAHEAD_HOURS = "lookahead_hours"
CONF_WATER_PRICE = "water_price"
CONF_WASTEWATER_PRICE = "wastewater_price"
CONF_WASTEWATER_ENABLED = "wastewater_enabled"

# Scheduling mode: static (fixed schedule + forecast window) or dynamic.
CONF_MODE = "mode"
MODE_STATIC = "static"
MODE_DYNAMIC = "dynamic"
MODES = (MODE_STATIC, MODE_DYNAMIC)

# Dynamic mode: rain shortly before/after the slot postpones, wet soil skips.
CONF_RAIN_SENSOR = "rain_sensor"
CONF_PAST_RAIN_MINUTES = "past_rain_minutes"
CONF_NEXT_RAIN_MINUTES = "next_rain_minutes"
CONF_NEXT_RAIN_MM = "next_rain_mm"
CONF_NEXT_RAIN_PROBABILITY = "next_rain_probability"
CONF_POSTPONE_MINUTES = "postpone_minutes"
CONF_MOISTURE_SENSORS = "moisture_sensors"
CONF_MOISTURE_THRESHOLD = "moisture_threshold"

DEFAULT_NAME = "Bewässerung"
DEFAULT_WINDOW_START = "06:00:00"
DEFAULT_WINDOW_END = "22:00:00"
DEFAULT_INTERVAL_HOURS = 24
DEFAULT_RAIN_THRESHOLD_MM = 2.0
DEFAULT_RAIN_PROBABILITY = 70
DEFAULT_LOOKAHEAD_HOURS = 12
DEFAULT_DURATION_MIN = 0
DEFAULT_WATER_PRICE = 0.0
DEFAULT_WASTEWATER_PRICE = 0.0
DEFAULT_WASTEWATER_ENABLED = True

MAX_DURATION_MIN = 240

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

RAIN_REFRESH_MINUTES = 30

STATUS_IDLE = "idle"
STATUS_WATERING = "watering"
STATUS_SKIPPED_RAIN = "skipped_rain"
STATUS_SKIPPED_NO_DURATION = "skipped_no_duration"
STATUS_ERROR = "error"
STATUS_POSTPONED = "postponed"
STATUS_SKIPPED_MOISTURE = "skipped_moisture"
STATUSES = [
    STATUS_IDLE,
    STATUS_WATERING,
    STATUS_SKIPPED_RAIN,
    STATUS_SKIPPED_NO_DURATION,
    STATUS_ERROR,
    STATUS_POSTPONED,
    STATUS_SKIPPED_MOISTURE,
]

# Weather conditions that count as rain when no rain sensor is configured.
RAINY_CONDITIONS = frozenset(
    {"rainy", "pouring", "lightning-rainy", "snowy-rainy", "hail"}
)
# Precipitation rate units (anything else in mm/in is treated as an amount).
RAIN_RATE_UNITS = frozenset({"mm/h", "in/h", "mm/d", "in/d"})

HISTORY_DAYS = 90
SOURCE_AUTO = "auto"
SOURCE_MANUAL = "manual"
RESULT_COMPLETED = "completed"
RESULT_STOPPED = "stopped"
RESULT_ERROR = "error"

SIGNAL_UPDATE = f"{DOMAIN}_update"

PANEL_URL = "irrigation"
STATIC_URL = f"/{DOMAIN}_static"

OPTION_KEYS = (
    CONF_VALVE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_INTERVAL_HOURS,
    CONF_RAIN_THRESHOLD_MM,
    CONF_RAIN_PROBABILITY,
    CONF_LOOKAHEAD_HOURS,
    CONF_WATER_ENTITY,
    CONF_WATER_PRICE,
    CONF_WASTEWATER_PRICE,
    CONF_WASTEWATER_ENABLED,
    CONF_MODE,
    CONF_RAIN_SENSOR,
    CONF_PAST_RAIN_MINUTES,
    CONF_NEXT_RAIN_MINUTES,
    CONF_NEXT_RAIN_MM,
    CONF_NEXT_RAIN_PROBABILITY,
    CONF_POSTPONE_MINUTES,
    CONF_MOISTURE_SENSORS,
    CONF_MOISTURE_THRESHOLD,
)

# Defaults for options added after the first release (missing in older entries).
OPTION_DEFAULTS = {
    CONF_WATER_ENTITY: None,
    CONF_WATER_PRICE: DEFAULT_WATER_PRICE,
    CONF_WASTEWATER_PRICE: DEFAULT_WASTEWATER_PRICE,
    CONF_WASTEWATER_ENABLED: DEFAULT_WASTEWATER_ENABLED,
    CONF_MODE: MODE_STATIC,
    CONF_RAIN_SENSOR: None,
    CONF_PAST_RAIN_MINUTES: 30,
    CONF_NEXT_RAIN_MINUTES: 60,
    CONF_NEXT_RAIN_MM: 0.5,
    CONF_NEXT_RAIN_PROBABILITY: 60,
    CONF_POSTPONE_MINUTES: 60,
    CONF_MOISTURE_SENSORS: [],
    CONF_MOISTURE_THRESHOLD: 60,
}
