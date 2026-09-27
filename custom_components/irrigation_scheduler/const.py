"""Constants for the Irrigation Scheduler integration."""

from __future__ import annotations

DOMAIN = "irrigation_scheduler"

CONF_VALVE_ENTITY = "valve_entity"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_START_TIME = "start_time"
CONF_INTERVAL_HOURS = "interval_hours"
CONF_RAIN_THRESHOLD_MM = "rain_threshold_mm"
CONF_RAIN_PROBABILITY = "rain_probability"
CONF_LOOKAHEAD_HOURS = "lookahead_hours"

DEFAULT_NAME = "Bewässerung"
DEFAULT_START_TIME = "06:00:00"
DEFAULT_INTERVAL_HOURS = 24
DEFAULT_RAIN_THRESHOLD_MM = 2.0
DEFAULT_RAIN_PROBABILITY = 70
DEFAULT_LOOKAHEAD_HOURS = 12
DEFAULT_DURATION_MIN = 0

MAX_DURATION_MIN = 240

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

RAIN_REFRESH_MINUTES = 30

STATUS_IDLE = "idle"
STATUS_WATERING = "watering"
STATUS_SKIPPED_RAIN = "skipped_rain"
STATUS_SKIPPED_NO_DURATION = "skipped_no_duration"
STATUS_ERROR = "error"
STATUSES = [
    STATUS_IDLE,
    STATUS_WATERING,
    STATUS_SKIPPED_RAIN,
    STATUS_SKIPPED_NO_DURATION,
    STATUS_ERROR,
]
