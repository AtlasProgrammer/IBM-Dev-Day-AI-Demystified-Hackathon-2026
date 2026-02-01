from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import CalendarBlock
from backend.services.timeutil import ceil_to_minutes, ensure_aware


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


async def get_busy_blocks(
    session: AsyncSession, *, user_id: int, window: TimeWindow
) -> list[CalendarBlock]:
    q = (
        select(CalendarBlock)
        .where(CalendarBlock.user_id == user_id)
        .where(and_(CalendarBlock.start < window.end, CalendarBlock.end > window.start))
        .order_by(CalendarBlock.start.asc())
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def is_user_free(
    session: AsyncSession,
    *,
    user_id: int,
    start: datetime,
    end: datetime,
) -> bool:
    start = ensure_aware(start)
    end = ensure_aware(end)

    q = (
        select(CalendarBlock.id)
        .where(CalendarBlock.user_id == user_id)
        .where(and_(CalendarBlock.start < end, CalendarBlock.end > start))
        .limit(1)
    )
    res = await session.execute(q)
    return res.scalar_one_or_none() is None


async def find_common_slot(
    session: AsyncSession,
    *,
    user_ids: list[int],
    window: TimeWindow,
    duration_minutes: int,
    step_minutes: int = 15,
) -> tuple[datetime, datetime] | None:
    if not user_ids:
        return None

    start = ensure_aware(window.start)
    end = ensure_aware(window.end)

    cursor = ceil_to_minutes(start, step_minutes)
    duration = timedelta(minutes=duration_minutes)
    while cursor + duration <= end:
        slot_start = cursor
        slot_end = cursor + duration

        ok = True
        for uid in user_ids:
            if not await is_user_free(session, user_id=uid, start=slot_start, end=slot_end):
                ok = False
                break

        if ok:
            return slot_start, slot_end

        cursor = cursor + timedelta(minutes=step_minutes)

    return None


async def find_common_slots(
    session: AsyncSession,
    *,
    user_ids: list[int],
    window: TimeWindow,
    duration_minutes: int,
    limit: int = 3,
    step_minutes: int = 15,
) -> list[tuple[datetime, datetime]]:
    if limit <= 0:
        return []

    slots: list[tuple[datetime, datetime]] = []
    if not user_ids:
        return slots

    start = ensure_aware(window.start)
    end = ensure_aware(window.end)

    cursor = ceil_to_minutes(start, step_minutes)
    duration = timedelta(minutes=duration_minutes)

    while cursor + duration <= end and len(slots) < limit:
        slot_start = cursor
        slot_end = cursor + duration

        ok = True
        for uid in user_ids:
            if not await is_user_free(session, user_id=uid, start=slot_start, end=slot_end):
                ok = False
                break

        if ok:
            slots.append((slot_start, slot_end))

        cursor = cursor + timedelta(minutes=step_minutes)

    return slots


async def block_time(
    session: AsyncSession, *, user_id: int, start: datetime, end: datetime, title: str
) -> CalendarBlock:
    b = CalendarBlock(user_id=user_id, start=ensure_aware(start), end=ensure_aware(end), title=title)
    session.add(b)
    await session.flush()
    return b

