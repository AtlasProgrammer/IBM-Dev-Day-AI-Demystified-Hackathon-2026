from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Candidate, CalendarBlock, User, UserRole
from backend.services.timeutil import now


async def seed_if_empty(session: AsyncSession) -> None:
    res = await session.execute(select(User.id).limit(1))
    if res.scalar_one_or_none() is not None:
        return

    users = [
        User(name="Ivan Engineer", email="ivan.engineer@example.com", role=UserRole.engineer, slack_handle="@ivan"),
        User(name="Olga Engineer", email="olga.engineer@example.com", role=UserRole.engineer, slack_handle="@olga"),
        User(name="Max TechLead", email="max.techlead@example.com", role=UserRole.tech_lead, slack_handle="@max"),
    ]
    session.add_all(users)
    await session.flush()

    cand = Candidate(
        name="Test Candidate",
        email="candidate@example.com",
        resume_text=(
            "Synthetic demo resume.\n"
            "- 5 years of Python\n"
            "- FastAPI, SQL\n"
            "- System design (basic)\n"
        ),
    )
    session.add(cand)
    await session.flush()

    base = now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)

    blocks = [
        CalendarBlock(user_id=users[0].id, start=base + timedelta(hours=1), end=base + timedelta(hours=2), title="Focus"),
        CalendarBlock(user_id=users[1].id, start=base + timedelta(hours=2), end=base + timedelta(hours=3), title="Meeting"),
        CalendarBlock(user_id=users[2].id, start=base + timedelta(hours=1, minutes=30), end=base + timedelta(hours=2, minutes=30), title="1:1"),
    ]
    session.add_all(blocks)
    await session.commit()

