from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.models import (
    ATSRecord,
    ATSStatus,
    ATSRecommendation,
    Candidate,
    Feedback,
    FeedbackDecision,
    Interview,
    InterviewParticipant,
    InterviewStatus,
    SchedulingOption,
    SchedulingRequest,
    SchedulingRequestStatus,
    User,
)
from backend.services.calendar import TimeWindow, block_time, find_common_slot, find_common_slots
from backend.services.llm import FeedbackItem, summarize_feedback
from backend.services.notifier import get_notifier
from backend.services.security import make_feedback_token, parse_feedback_token
from backend.services.timeutil import now


@dataclass(frozen=True)
class StartResult:
    interview: Interview


@dataclass(frozen=True)
class ProposalResult:
    request: SchedulingRequest
    options: list[SchedulingOption]


def _video_link(interview_id: int) -> str:
    room = f"ibm-dev-day-{interview_id}-{secrets.token_hex(4)}"
    return f"https://meet.jit.si/{room}"


async def start_interview(
    session: AsyncSession,
    *,
    recruiter_name: str,
    recruiter_email: str,
    candidate_id: int,
    job_title: str,
    interviewer_user_ids: list[int],
    preferred_window: TimeWindow,
    duration_minutes: int,
) -> StartResult:
    cand = await session.get(Candidate, candidate_id)
    if not cand:
        raise ValueError("candidate not found")

    if not interviewer_user_ids:
        raise ValueError("no interviewers specified")
    q = select(User).where(User.id.in_(interviewer_user_ids))
    res = await session.execute(q)
    users = list(res.scalars().all())
    if len(users) != len(set(interviewer_user_ids)):
        raise ValueError("some interviewers not found")

    slot = await find_common_slot(
        session,
        user_ids=interviewer_user_ids,
        window=preferred_window,
        duration_minutes=duration_minutes,
        step_minutes=15,
    )
    if not slot:
        raise ValueError("no common slot found in preferred window")

    start_dt, end_dt = slot
    interview = Interview(
        candidate_id=candidate_id,
        job_title=job_title,
        recruiter_name=recruiter_name,
        recruiter_email=recruiter_email,
        created_at=now(),
        scheduled_start=start_dt,
        scheduled_end=end_dt,
        video_link="pending",
        status=InterviewStatus.scheduled,
    )
    session.add(interview)
    await session.flush()

    interview.video_link = _video_link(interview.id)

    for uid in interviewer_user_ids:
        session.add(InterviewParticipant(interview_id=interview.id, user_id=uid))

    ats = ATSRecord(
        interview_id=interview.id,
        status=ATSStatus.interview_scheduled,
        recommendation=None,
        summary=None,
        updated_at=now(),
    )
    session.add(ats)

    for u in users:
        await block_time(
            session,
            user_id=u.id,
            start=start_dt,
            end=end_dt,
            title=f"Interview: {cand.name} ({job_title})",
        )

    await session.commit()

    notifier = get_notifier()
    when = f"{start_dt:%Y-%m-%d %H:%M}–{end_dt:%H:%M} ({settings.timezone})"
    subject = f"Interview scheduled: {cand.name} - {job_title}"
    body_common = (
        "Interview scheduled.\n\n"
        f"Candidate: {cand.name}\n"
        f"Job: {job_title}\n"
        f"When: {when}\n"
        f"Link: {interview.video_link}\n\n"
        f"Resume (short):\n{cand.resume_text}\n"
    )
    await notifier.send_email(to=cand.email, subject=subject, body=body_common)
    for u in users:
        await notifier.send_email(to=u.email, subject=subject, body=body_common)

    await notifier.send_slack(
        text=f"Interview scheduled: {cand.name} - {job_title}, {when}. Link: {interview.video_link}"
    )

    return StartResult(interview=interview)


async def propose_schedule(
    session: AsyncSession,
    *,
    recruiter_name: str,
    recruiter_email: str,
    candidate_id: int,
    job_title: str,
    interviewer_user_ids: list[int],
    preferred_window: TimeWindow,
    duration_minutes: int,
    option_limit: int = 3,
) -> ProposalResult:
    cand = await session.get(Candidate, candidate_id)
    if not cand:
        raise ValueError("candidate not found")

    if not interviewer_user_ids:
        raise ValueError("no interviewers specified")
    q = select(User).where(User.id.in_(interviewer_user_ids))
    res = await session.execute(q)
    users = list(res.scalars().all())
    if len(users) != len(set(interviewer_user_ids)):
        raise ValueError("some interviewers not found")

    slots = await find_common_slots(
        session,
        user_ids=interviewer_user_ids,
        window=preferred_window,
        duration_minutes=duration_minutes,
        limit=option_limit,
        step_minutes=15,
    )
    if not slots:
        raise ValueError("no common slots found in preferred window")

    req = SchedulingRequest(
        created_at=now(),
        recruiter_name=recruiter_name,
        recruiter_email=recruiter_email,
        candidate_id=candidate_id,
        job_title=job_title,
        duration_minutes=duration_minutes,
        status=SchedulingRequestStatus.proposed,
    )
    session.add(req)
    await session.flush()

    options: list[SchedulingOption] = []
    for s, e in slots:
        opt = SchedulingOption(request_id=req.id, start=s, end=e)
        session.add(opt)
        options.append(opt)

    await session.commit()
    return ProposalResult(request=req, options=options)


async def approve_schedule_and_create_interview(
    session: AsyncSession,
    *,
    request_id: int,
    option_id: int,
    interviewer_user_ids: list[int],
) -> StartResult:
    req = await session.get(SchedulingRequest, request_id)
    if not req:
        raise ValueError("request not found")
    if req.status != SchedulingRequestStatus.proposed:
        raise ValueError("request not in proposed state")

    opt = await session.get(SchedulingOption, option_id)
    if not opt or opt.request_id != req.id:
        raise ValueError("invalid option_id for request")

    cand = await session.get(Candidate, req.candidate_id)
    if not cand:
        raise ValueError("candidate not found")

    q = select(User).where(User.id.in_(interviewer_user_ids))
    res = await session.execute(q)
    users = list(res.scalars().all())
    if len(users) != len(set(interviewer_user_ids)):
        raise ValueError("some interviewers not found")

    interview = Interview(
        candidate_id=req.candidate_id,
        job_title=req.job_title,
        recruiter_name=req.recruiter_name,
        recruiter_email=req.recruiter_email,
        created_at=now(),
        scheduled_start=opt.start,
        scheduled_end=opt.end,
        video_link="pending",
        status=InterviewStatus.scheduled,
    )
    session.add(interview)
    await session.flush()
    interview.video_link = _video_link(interview.id)

    for uid in interviewer_user_ids:
        session.add(InterviewParticipant(interview_id=interview.id, user_id=uid))

    session.add(
        ATSRecord(
            interview_id=interview.id,
            status=ATSStatus.interview_scheduled,
            recommendation=None,
            summary=None,
            updated_at=now(),
        )
    )

    for u in users:
        await block_time(
            session,
            user_id=u.id,
            start=interview.scheduled_start,
            end=interview.scheduled_end,
            title=f"Interview: {cand.name} ({req.job_title})",
        )

    req.status = SchedulingRequestStatus.approved
    req.approved_option_id = opt.id
    req.interview_id = interview.id

    await session.commit()

    notifier = get_notifier()
    when = f"{interview.scheduled_start:%Y-%m-%d %H:%M}–{interview.scheduled_end:%H:%M} ({settings.timezone})"
    subject = f"Interview scheduled: {cand.name} - {req.job_title}"
    body_common = (
        "Interview scheduled.\n\n"
        f"Candidate: {cand.name}\n"
        f"Job: {req.job_title}\n"
        f"When: {when}\n"
        f"Link: {interview.video_link}\n\n"
        f"Resume (short):\n{cand.resume_text}\n"
    )
    await notifier.send_email(to=cand.email, subject=subject, body=body_common)
    for u in users:
        await notifier.send_email(to=u.email, subject=subject, body=body_common)
    await notifier.send_slack(text=f"Interview scheduled: {cand.name} - {req.job_title}, {when}. Link: {interview.video_link}")

    return StartResult(interview=interview)


async def request_feedback(session: AsyncSession, *, interview_id: int) -> None:
    interview = await session.get(Interview, interview_id)
    if not interview:
        return

    cand = await session.get(Candidate, interview.candidate_id)
    if not cand:
        return

    q = (
        select(User)
        .join(InterviewParticipant, InterviewParticipant.user_id == User.id)
        .where(InterviewParticipant.interview_id == interview_id)
    )
    res = await session.execute(q)
    users = list(res.scalars().all())

    notifier = get_notifier()
    for u in users:
        token = make_feedback_token(interview_id=interview_id, user_id=u.id)
        url = f"{settings.base_url}/f/{token}"
        subject = f"Feedback requested: {cand.name} - {interview.job_title}"
        body = (
            "Please leave your interview feedback.\n\n"
            f"Candidate: {cand.name}\n"
            f"Job: {interview.job_title}\n"
            f"Feedback form: {url}\n"
        )
        await notifier.send_email(to=u.email, subject=subject, body=body)
        await notifier.send_slack(text=f"Feedback: {u.name} -> {url}")

    interview.status = InterviewStatus.feedback_requested
    interview.feedback_requested_at = now()
    q_ats = select(ATSRecord).where(ATSRecord.interview_id == interview.id)
    res_ats = await session.execute(q_ats)
    ats = res_ats.scalar_one_or_none()
    if ats:
        ats.status = ATSStatus.interview_completed
        ats.updated_at = now()
    await session.commit()


async def submit_feedback(
    session: AsyncSession, *, token: str, decision: str, comment: str
) -> None:
    interview_id, user_id = parse_feedback_token(token)
    interview = await session.get(Interview, interview_id)
    if not interview:
        raise ValueError("interview not found")

    dec_map = {
        "pass": FeedbackDecision.pass_,
        "fail": FeedbackDecision.fail,
        "need_more_info": FeedbackDecision.need_more_info,
    }
    if decision not in dec_map:
        raise ValueError("invalid decision")

    q = select(Feedback).where(Feedback.interview_id == interview_id, Feedback.user_id == user_id)
    res = await session.execute(q)
    fb = res.scalar_one_or_none()
    if fb is None:
        fb = Feedback(
            interview_id=interview_id,
            user_id=user_id,
            decision=dec_map[decision],
            comment=comment or "",
            submitted_at=now(),
        )
        session.add(fb)
    else:
        fb.decision = dec_map[decision]
        fb.comment = comment or ""
        fb.submitted_at = now()

    await session.commit()


async def maybe_consolidate(session: AsyncSession, *, interview_id: int) -> bool:
    interview = await session.get(Interview, interview_id)
    if not interview:
        return False

    cand = await session.get(Candidate, interview.candidate_id)
    if not cand:
        return False

    q_users = (
        select(User)
        .join(InterviewParticipant, InterviewParticipant.user_id == User.id)
        .where(InterviewParticipant.interview_id == interview_id)
    )
    res_u = await session.execute(q_users)
    users = list(res_u.scalars().all())
    required_user_ids = {u.id for u in users}

    q_fb = select(Feedback).where(Feedback.interview_id == interview_id)
    res_f = await session.execute(q_fb)
    feedback = list(res_f.scalars().all())
    got_user_ids = {f.user_id for f in feedback}

    if not required_user_ids.issubset(got_user_ids):
        return False

    id_to_user = {u.id: u for u in users}
    items = [
        FeedbackItem(
            interviewer_name=id_to_user[f.user_id].name if f.user_id in id_to_user else f"User {f.user_id}",
            decision=f.decision,
            comment=f.comment,
        )
        for f in feedback
    ]
    summary = await summarize_feedback(
        candidate_name=cand.name,
        job_title=interview.job_title,
        items=items,
    )

    q_ats = select(ATSRecord).where(ATSRecord.interview_id == interview.id)
    res_ats = await session.execute(q_ats)
    ats = res_ats.scalar_one_or_none()
    if ats:
        ats.status = ATSStatus.feedback_received
        ats.recommendation = summary.recommendation
        ats.summary = summary.narrative
        ats.updated_at = now()
    else:
        session.add(
            ATSRecord(
                interview_id=interview.id,
                status=ATSStatus.feedback_received,
                recommendation=summary.recommendation,
                summary=summary.narrative,
                updated_at=now(),
            )
        )

    interview.status = InterviewStatus.feedback_received
    interview.consolidated_at = now()
    await session.commit()

    notifier = get_notifier()
    subject = f"Interview report: {cand.name} - {interview.job_title}"
    body = (
        "Report generated.\n\n"
        f"Candidate: {cand.name}\n"
        f"Job: {interview.job_title}\n"
        f"Recommendation: {summary.recommendation.value}\n\n"
        f"{summary.narrative}\n"
        f"\nReport link: {settings.base_url}/reports/{interview.id}\n"
    )
    await notifier.send_email(to=interview.recruiter_email, subject=subject, body=body)
    await notifier.send_slack(text=f"Report ready: {cand.name} - {summary.recommendation.value}")

    return True


async def send_reminder(session: AsyncSession, *, interview_id: int) -> None:
    interview = await session.get(Interview, interview_id)
    if not interview:
        return

    cand = await session.get(Candidate, interview.candidate_id)
    if not cand:
        return

    q = (
        select(User)
        .join(InterviewParticipant, InterviewParticipant.user_id == User.id)
        .where(InterviewParticipant.interview_id == interview_id)
    )
    res = await session.execute(q)
    users = list(res.scalars().all())

    notifier = get_notifier()
    when = f"{interview.scheduled_start:%Y-%m-%d %H:%M} ({settings.timezone})"
    text = (
        "Reminder: your interview starts soon.\n"
        f"Candidate: {cand.name}\n"
        f"Job: {interview.job_title}\n"
        f"When: {when}\n"
        f"Link: {interview.video_link}\n"
        f"Resume:\n{cand.resume_text}"
    )
    for u in users:
        await notifier.send_email(to=u.email, subject=f"Reminder: {cand.name}", body=text)
    await notifier.send_slack(text=f"Reminder: {cand.name} @ {when} -> {interview.video_link}")

    interview.reminder_sent_at = now()
    await session.commit()

