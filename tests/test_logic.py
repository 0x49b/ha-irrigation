"""Tests for the pure logic module (no Home Assistant needed)."""

from datetime import datetime, time, timedelta
import importlib.util
from pathlib import Path
import sys
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


ALL_DAYS = range(7)


def windows(start, end, days=ALL_DAYS):
    return {d: (start, end) for d in days}


# 2026-07-01 is a Wednesday (weekday 2).
@pytest.mark.parametrize(
    ("now", "win", "interval", "expected"),
    [
        (dt(1, 5), windows(time(7), time(22)), 6, (dt(1, 7), 2)),
        (dt(1, 7), windows(time(7), time(22)), 6, (dt(1, 13), 2)),
        (dt(1, 19), windows(time(7), time(22)), 6, (dt(2, 7), 3)),  # 01:00 would be outside
        (dt(1, 7), windows(time(7), time(22)), 24, (dt(2, 7), 3)),
        (dt(1, 21, 59), windows(time(7), time(21, 59)), 1, (dt(2, 7), 3)),  # end is exclusive
        # Overnight window 22:00-04:00, slots belong to the day the window starts.
        (dt(1, 23), windows(time(22), time(4)), 2, (dt(2, 0), 2)),
        (dt(2, 3), windows(time(22), time(4), days=[2]), 2, (dt(8, 22), 2)),
        # Only Monday active -> next Monday.
        (dt(1, 12), windows(time(7), time(22), days=[0]), 6, (dt(6, 7), 0)),
        # start == end means 24h window.
        (dt(1, 23), windows(time(6), time(6)), 12, (dt(2, 6), 3)),
        # Different windows per day.
        (dt(1, 20), {2: (time(7), time(12)), 3: (time(9), time(10))}, 2, (dt(2, 9), 3)),
    ],
)
def test_compute_next_run(now, win, interval, expected):
    assert logic.compute_next_run(now, win, interval) == expected


def test_compute_next_run_no_active_day():
    assert logic.compute_next_run(dt(1, 1), {}, 6) is None


def test_compute_next_run_invalid():
    with pytest.raises(ValueError):
        logic.compute_next_run(dt(1, 1), windows(time(6), time(22)), 0)


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


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [(100.0, 135.5, 35.5), (100.0, 100.0, 0.0), (100.0, 12.0, 12.0)],
)
def test_meter_consumption(start, end, expected):
    assert logic.meter_consumption(start, end) == expected


@pytest.mark.parametrize(
    ("liters", "price", "expected"),
    [(1000, 2.5, 2.5), (38.4, 4.9, 0.19), (0, 5, 0), (250, 0, 0)],
)
def test_water_cost(liters, price, expected):
    assert logic.water_cost(liters, price) == expected


RAINY = frozenset({"rainy", "pouring"})


@pytest.mark.parametrize(
    ("kind", "values", "expected"),
    [
        ("binary", ["off", "on", "off"], True),
        ("binary", ["off", "unavailable"], False),
        ("condition", ["sunny", "pouring", "cloudy"], True),
        ("condition", ["sunny", "cloudy"], False),
        ("rate", ["0", "0.0", "1.2"], True),
        ("rate", ["0", "unknown"], False),
        ("amount", ["4.2", "4.2", "4.5"], True),
        ("amount", ["4.2", "4.2"], False),
        ("amount", ["12.0", "0.0"], False),  # daily reset only
        ("amount", ["12.0", "0.0", "0.3"], True),  # reset, then rain
        ("amount", [], False),
    ],
)
def test_rained_recently(kind, values, expected):
    assert logic.rained_recently(kind, values, RAINY) is expected


@pytest.mark.parametrize(
    ("slot", "start", "end", "expected"),
    [
        (dt(1, 7), time(7), time(22), dt(1, 22)),
        (dt(1, 13), time(7), time(22), dt(1, 22)),
        (dt(1, 23), time(22), time(4), dt(2, 4)),
        (dt(2, 2), time(22), time(4), dt(2, 4)),  # overnight part, previous day's window
        (dt(1, 6), time(6), time(6), dt(2, 6)),  # 24h window
    ],
)
def test_window_end_for_slot(slot, start, end, expected):
    assert logic.window_end_for_slot(slot, start, end) == expected


def test_postpone_target():
    now = dt(1, 13)
    assert logic.postpone_target(now, 60, dt(1, 22), dt(1, 19)) == dt(1, 14)
    assert logic.postpone_target(dt(1, 21, 30), 60, dt(1, 22), None) is None  # past window end
    assert logic.postpone_target(dt(1, 18, 30), 60, dt(1, 22), dt(1, 19)) is None  # hits next slot
    assert logic.postpone_target(dt(1, 20), 60, dt(1, 22), None) == dt(1, 21)


def test_average():
    assert logic.average([50, 70, None]) == 60
    assert logic.average([None]) is None


def test_upcoming_slots():
    # Wednesday 2026-07-01 12:00, Wed/Thu active 07-22 every 6h.
    win = windows(time(7), time(22), days=[2, 3])
    slots = logic.upcoming_slots(dt(1, 12), win, 6, 7)
    assert slots[:5] == [(dt(1, 13), 2), (dt(1, 19), 2), (dt(2, 7), 3), (dt(2, 13), 3), (dt(2, 19), 3)]
    # Next active Wednesday is within 7 days, the slot exactly at the horizon is included.
    assert (dt(8, 7), 2) in slots and (dt(8, 13), 2) not in slots
    assert slots == sorted(slots)


def test_upcoming_slots_overnight_window_belongs_to_start_day():
    slots = logic.upcoming_slots(dt(1, 21), windows(time(22), time(4), days=[2]), 3, 1)
    assert slots == [(dt(1, 22), 2), (dt(2, 1), 2)]


def test_upcoming_matches_compute_next_run():
    win = windows(time(7), time(22))
    for hour in range(24):
        now = dt(1, hour, 30)
        assert logic.upcoming_slots(now, win, 5, 7)[0] == logic.compute_next_run(now, win, 5)
