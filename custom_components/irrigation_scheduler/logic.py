"""Pure scheduling and rain evaluation logic (no Home Assistant imports)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

ONE_DAY = timedelta(days=1)


def _slots_for_day(day: date, start: time, interval: timedelta, tz) -> list[datetime]:
    """Return all run slots anchored at `start` on `day`, spanning 24 hours."""
    base = datetime.combine(day, start, tzinfo=tz)
    slots = []
    offset = timedelta(0)
    while offset < ONE_DAY:
        slots.append(base + offset)
        offset += interval
    return slots


def compute_next_run(now: datetime, start: time, interval_hours: float) -> datetime:
    """Return the first slot strictly after `now`.

    Slots are `start + k * interval` for every day, restarting at `start`
    each day. With intervals that divide 24 this is a regular grid; other
    intervals are re-anchored daily at `start`.
    """
    if interval_hours <= 0:
        raise ValueError("interval_hours must be positive")
    interval = timedelta(hours=interval_hours)
    tz = now.tzinfo
    today = now.date()
    candidates: list[datetime] = []
    for delta in (-1, 0, 1):
        candidates.extend(_slots_for_day(today + timedelta(days=delta), start, interval, tz))
    return min(slot for slot in candidates if slot > now)


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
