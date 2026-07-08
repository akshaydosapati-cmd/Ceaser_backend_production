from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TIME_PRESETS = {
    "morning": time(9, 0),
    "afternoon": time(14, 0),
    "evening": time(18, 0),
}


def normalize_timezone(value: str | None) -> str:
    if not value:
        return "UTC"
    try:
        ZoneInfo(value)
        return value
    except ZoneInfoNotFoundError:
        return "UTC"


def parse_trigger_time(value: str | None) -> time:
    if not value:
        return TIME_PRESETS["morning"]
    lowered = value.lower().strip()
    if lowered in TIME_PRESETS:
        return TIME_PRESETS[lowered]
    try:
        hour, minute = lowered.split(":", 1)
        return time(int(hour), int(minute[:2]))
    except (ValueError, TypeError):
        return TIME_PRESETS["morning"]


def next_run_at(*, frequency: str, trigger_time: str | None, tz_name: str | None, from_time: datetime | None = None) -> datetime | None:
    frequency = frequency.lower()
    if frequency == "custom":
        frequency = "daily"
    if frequency not in {"once", "daily", "weekly", "monthly", "every_weekday"}:
        frequency = "daily"

    tz = ZoneInfo(normalize_timezone(tz_name))
    now = (from_time or datetime.now(timezone.utc)).astimezone(tz)
    target_time = parse_trigger_time(trigger_time)
    candidate = datetime.combine(now.date(), target_time, tzinfo=tz)

    if candidate <= now:
        if frequency in {"once", "daily", "every_weekday"}:
            candidate += timedelta(days=1)
        elif frequency == "weekly":
            candidate += timedelta(days=7)
        elif frequency == "monthly":
            year = candidate.year + (1 if candidate.month == 12 else 0)
            month = 1 if candidate.month == 12 else candidate.month + 1
            day = min(candidate.day, 28)
            candidate = candidate.replace(year=year, month=month, day=day)

    if frequency == "every_weekday":
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)

    return candidate.astimezone(timezone.utc)
