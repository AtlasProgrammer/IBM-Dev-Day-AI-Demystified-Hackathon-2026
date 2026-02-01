from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select

from backend.db import Base, SessionLocal, engine
from backend.models import ATSRecord, Candidate, Interview, User
from backend.seed import seed_if_empty
from backend.services.calendar import TimeWindow
from backend.services.orchestrator import maybe_consolidate, request_feedback, start_interview, submit_feedback
from backend.services.security import make_feedback_token
from backend.services.timeutil import now


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        await seed_if_empty(session)

        cand = (await session.execute(select(Candidate).order_by(Candidate.id.asc()))).scalars().first()
        users = list((await session.execute(select(User).order_by(User.id.asc()))).scalars().all())
        assert cand and len(users) >= 2

        w_start = (now() + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
        w_end = w_start + timedelta(hours=6)

        r = await start_interview(
            session,
            recruiter_name="Recruiter",
            recruiter_email="recruiter@example.com",
            candidate_id=cand.id,
            job_title="Backend Engineer",
            interviewer_user_ids=[u.id for u in users],
            preferred_window=TimeWindow(start=w_start, end=w_end),
            duration_minutes=60,
        )

        interview_id = r.interview.id
        await request_feedback(session, interview_id=interview_id)

        for idx, u in enumerate(users):
            token = make_feedback_token(interview_id=interview_id, user_id=u.id)
            decision = "pass" if idx % 2 == 0 else "need_more_info"
            comment = f"Comment from {u.name}: demo evaluation."
            await submit_feedback(session, token=token, decision=decision, comment=comment)

        done = await maybe_consolidate(session, interview_id=interview_id)
        assert done

        it = await session.get(Interview, interview_id)
        ats = (await session.execute(select(ATSRecord).where(ATSRecord.interview_id == interview_id))).scalar_one()
        print(f"OK: interview={it.id} status={it.status.value}")
        print(f"ATS: {ats.status.value}, recommendation={ats.recommendation.value if ats.recommendation else None}")
        print("SUMMARY:")
        print(ats.summary or "")


if __name__ == "__main__":
    asyncio.run(main())

