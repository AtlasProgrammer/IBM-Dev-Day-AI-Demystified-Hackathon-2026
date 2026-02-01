from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from backend.core.config import settings
from backend.db import SessionLocal
from backend.models import Interview, InterviewStatus
from backend.services.orchestrator import maybe_consolidate, request_feedback, send_reminder
from backend.services.timeutil import now


async def tick() -> None:
    t = now()

    async with SessionLocal() as session:
        lead = timedelta(minutes=settings.reminder_lead_minutes)
        due_by = t + lead
        q = (
            select(Interview.id)
            .where(Interview.status == InterviewStatus.scheduled)
            .where(Interview.reminder_sent_at.is_(None))
            .where(Interview.scheduled_start <= due_by)
            .where(Interview.scheduled_start > t)
        )
        res = await session.execute(q)
        for interview_id in list(res.scalars().all()):
            await send_reminder(session, interview_id=interview_id)

        delay = timedelta(minutes=settings.feedback_request_delay_minutes)
        q2 = (
            select(Interview.id)
            .where(Interview.feedback_requested_at.is_(None))
            .where(Interview.scheduled_end <= t - delay)
        )
        res2 = await session.execute(q2)
        for interview_id in list(res2.scalars().all()):
            await request_feedback(session, interview_id=interview_id)

        q3 = (
            select(Interview.id)
            .where(Interview.status.in_([InterviewStatus.feedback_requested, InterviewStatus.completed]))
            .where(Interview.consolidated_at.is_(None))
        )
        res3 = await session.execute(q3)
        for interview_id in list(res3.scalars().all()):
            await maybe_consolidate(session, interview_id=interview_id)

