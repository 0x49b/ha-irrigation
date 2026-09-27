"""Pure scheduling and rain evaluation logic (no Home Assistant imports)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

ONE_DAY = timedelta(days=1)


def window_slots(
    day: date, start: time, end: time, interval: timedelta, tz
) -> list[datetime]:
    """Return run slots `start + k * interval` that begin before `end` on `day`.

    If `end <= start` the window extends past midnight into the next day
    (`start == end` means a full 24 hours).
    """
    slot = datetime.combine(day, start, tzinfo=tz)
    window_end = datetime.combine(day, end, tzinfo=tz)
    if window_end <= slot:
        window_end += ONE_DAY
    slots = []
    while slot < window_end:
        slots.append(slot)
        slot += interval
    return slots


def compute_next_run(
    now: datetime,
    windows: Mapping[int, tuple[time, time]],
    interval_hours: float,
) -> tuple[datetime, int] | None:
    """Return the first slot strictly after `now` and the weekday it belongs to.

    `windows` maps weekday (0 = Monday) to its (start, end) window. Weekdays
    missing from the mapping get no runs. Returns None if no weekday is active.
    """
    if interval_hours <= 0:
        raise ValueError("interval_hours must be positive")
    interval = timedelta(hours=interval_hours)
    today = now.date()
    best: tuple[datetime, int] | None = None
    # Start one day back to catch windows that run past midnight.
    for delta in range(-1, 8):
        day = today + timedelta(days=delta)
        weekday = day.weekday()
        if weekday not in windows:
            continue
        start, end = windows[weekday]
        for slot in window_slots(day, start, end, interval, now.tzinfo):
            if slot > now and (best is None or slot < best[0]):
                best = (slot, weekday)
                break
    return best


@dataclass(frozen=True)
class RainAssessment:
    """Result of evaluating a forecast."""

    amount_mm: float
    max_probability: float | None
    skip: bool


def _parse_dt(value: Any, tz) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def assess_rain(
    forecast: Iterable[Mapping[str, Any]],
    now: datetime,
    lookahead_hours: float,
    threshold_mm: float,
    threshold_probability: float,
    period: timedelta = timedelta(hours=1),
) -> RainAssessment:
    """Sum precipitation and take max probability of entries overlapping the window.

    Each forecast entry covers `[datetime, datetime + period)`. A threshold of
    0 disables that criterion.
    """
    window_end = now + timedelta(hours=lookahead_hours)
    amount = 0.0
    max_prob: float | None = None
    for entry in forecast:
        start = _parse_dt(entry.get("datetime"), now.tzinfo)
        if start is None or start >= window_end or start + period <= now:
            continue
        precipitation = entry.get("precipitation")
        if precipitation is not None:
            amount += float(precipitation)
        probability = entry.get("precipitation_probability")
        if probability is not None:
            max_prob = max(float(probability), max_prob or 0.0)

    skip = (threshold_mm > 0 and amount >= threshold_mm) or (
        threshold_probability > 0
        and max_prob is not None
        and max_prob >= threshold_probability
    )
    return RainAssessment(round(amount, 2), max_prob, skip)
