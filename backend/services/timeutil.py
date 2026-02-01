from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.core.config import settings


def tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def now() -> datetime:
    return datetime.now(tz())


def ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz())
    return dt


def ceil_to_minutes(dt: datetime, minutes: int) -> datetime:
    dt = ensure_aware(dt)
    delta = timedelta(minutes=minutes)
    epoch = datetime(1970, 1, 1, tzinfo=dt.tzinfo)
    seconds = (dt - epoch).total_seconds()
    step = delta.total_seconds()
    snapped = ((seconds + step - 1) // step) * step
    return epoch + timedelta(seconds=snapped)

