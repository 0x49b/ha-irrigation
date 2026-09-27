"""Tests for the pure logic module (no Home Assistant needed)."""

from datetime import datetime, time, timedelta
import importlib.util
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_spec = importlib.util.spec_from_file_location(
    "logic",
    Path(__file__).parents[1] / "custom_components/irrigation_scheduler/logic.py",
)
logic = importlib.util.module_from_spec(_spec)
sys.modules["logic"] = logic
_spec.loader.exec_module(logic)

TZ = ZoneInfo("Europe/Berlin")


def dt(day, hour, minute=0):
    return datetime(2026, 7, day, hour, minute, tzinfo=TZ)


@pytest.mark.parametrize(
    ("now", "start", "interval", "expected"),
    [
        (dt(1, 5), time(6), 24, dt(1, 6)),
        (dt(1, 6), time(6), 24, dt(2, 6)),
        (dt(1, 7), time(6), 12, dt(1, 18)),
        (dt(1, 19), time(6), 12, dt(2, 6)),
        (dt(1, 1), time(22), 6, dt(1, 4)),  # slot from previous day's cycle
        (dt(1, 22, 30), time(6), 5, dt(2, 2)),  # 6,11,16,21,2 then re-anchor at 6
        (dt(2, 3), time(6), 5, dt(2, 6)),
        (dt(1, 12), time(6), 5, dt(1, 16)),
    ],
)
def test_compute_next_run(now, start, interval, expected):
    assert logic.compute_next_run(now, start, interval) == expected


def test_compute_next_run_invalid():
    with pytest.raises(ValueError):
        logic.compute_next_run(dt(1, 1), time(6), 0)


def hourly(now, values):
    return [
        {
            "datetime": (now + timedelta(hours=i)).isoformat(),
            "precipitation": mm,
            "precipitation_probability": p,
        }
        for i, (mm, p) in enumerate(values)
    ]


def test_assess_rain_amount_skip():
    now = dt(1, 6)
    fc = hourly(now, [(0.5, 20), (1.0, 40), (1.0, 40), (5.0, 90)])
    res = logic.assess_rain(fc, now, 3, 2.0, 0)
    assert res.amount_mm == 2.5
    assert res.max_probability == 40
    assert res.skip


def test_assess_rain_probability_skip():
    now = dt(1, 6)
    fc = hourly(now, [(0, 20), (0.1, 80)])
    assert logic.assess_rain(fc, now, 12, 0, 70).skip
    assert not logic.assess_rain(fc, now, 12, 5, 0).skip


def test_assess_rain_ignores_outside_window():
    now = dt(1, 6)
    fc = hourly(now - timedelta(hours=3), [(10, 100)] * 2 + [(0, 0)] * 10)
    res = logic.assess_rain(fc, now, 3, 1, 50)
    assert res.amount_mm == 0
    assert not res.skip


def test_assess_rain_partial_hour_counts():
    now = dt(1, 6, 30)
    fc = hourly(dt(1, 6), [(3, 50)])
    assert logic.assess_rain(fc, now, 1, 2, 0).skip


def test_assess_rain_daily():
    now = dt(1, 18)
    fc = [
        {"datetime": "2026-07-01T00:00:00+02:00", "precipitation": 4, "precipitation_probability": 60},
        {"datetime": "2026-07-02T00:00:00+02:00", "precipitation": 1},
        {"datetime": "2026-07-03T00:00:00+02:00", "precipitation": 20},
    ]
    res = logic.assess_rain(fc, now, 12, 10, 0, timedelta(days=1))
    assert res.amount_mm == 5
    assert not res.skip


def test_assess_rain_missing_values():
    now = dt(1, 6)
    fc = [{"datetime": now.isoformat()}, {"datetime": None}, {"datetime": "garbage"}]
    res = logic.assess_rain(fc, now, 12, 1, 50)
    assert res == logic.RainAssessment(0, None, False)
