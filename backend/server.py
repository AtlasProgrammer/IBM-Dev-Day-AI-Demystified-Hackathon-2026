from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db import Base, engine, get_session
from backend.models import ATSRecord, Candidate, Interview, InterviewParticipant, SchedulingOption, SchedulingRequest, User
from backend.schemas import (
    ApproveScheduleRequest,
    ApproveScheduleResponse,
    CandidateOut,
    InterviewOut,
    InterviewParticipantOut,
    ProposeScheduleRequest,
    ProposeScheduleResponse,
    SchedulingOptionOut,
    StartInterviewRequest,
    StartInterviewResponse,
    SubmitFeedbackRequest,
    SubmitFeedbackResponse,
    UserOut,
)
from backend.seed import seed_if_empty
from backend.services.calendar import TimeWindow
from backend.services.jobs import tick
from backend.services.orchestrator import (
    approve_schedule_and_create_interview,
    propose_schedule,
    start_interview,
    submit_feedback,
)
from backend.services.timeutil import ensure_aware, now, tz


_base_url = (settings.base_url or "").rstrip("/")
app = FastAPI(title=settings.app_name, servers=[{"url": _base_url}])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

scheduler: AsyncIOScheduler | None = None


@app.on_event("startup")
async def on_startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if settings.seed_on_startup:
        from backend.db import SessionLocal

        async with SessionLocal() as session:
            await seed_if_empty(session)

    global scheduler
    scheduler = AsyncIOScheduler(timezone=str(tz()))
    scheduler.add_job(tick, "interval", seconds=30, id="tick")
    scheduler.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        scheduler = None


async def _interview_out(session: AsyncSession, interview: Interview) -> InterviewOut:
    cand = await session.get(Candidate, interview.candidate_id)
    if not cand:
        raise HTTPException(500, "candidate missing")

    q = (
        select(User)
        .join(InterviewParticipant, InterviewParticipant.user_id == User.id)
        .where(InterviewParticipant.interview_id == interview.id)
    )
    res = await session.execute(q)
    users = list(res.scalars().all())

    participants = [
        InterviewParticipantOut(user_id=u.id, name=u.name, email=u.email, role=u.role.value) for u in users
    ]

    res_ats = await session.execute(select(ATSRecord).where(ATSRecord.interview_id == interview.id))
    ats = res_ats.scalar_one_or_none()

    report_url = f"/reports/{interview.id}" if (ats and ats.summary) else None
    if report_url is None and interview.status.value == "feedback_received":
        report_url = f"/reports/{interview.id}"

    return InterviewOut(
        id=interview.id,
        job_title=interview.job_title,
        status=interview.status.value,
        scheduled_start=interview.scheduled_start,
        scheduled_end=interview.scheduled_end,
        video_link=interview.video_link,
        recruiter_name=interview.recruiter_name,
        recruiter_email=interview.recruiter_email,
        candidate_id=cand.id,
        candidate_name=cand.name,
        candidate_email=cand.email,
        participants=participants,
        report_url=report_url,
    )


def _parse_iso(s: str) -> datetime:
    try:
        dt = datetime.fromisoformat(s)
    except Exception as e:
        raise HTTPException(400, f"invalid datetime: {s}") from e
    return ensure_aware(dt)


@app.get("/", response_class=HTMLResponse)
async def ui_index(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    res_u = await session.execute(select(User).order_by(User.id.asc()))
    users = list(res_u.scalars().all())
    res_c = await session.execute(select(Candidate).order_by(Candidate.id.asc()))
    candidates = list(res_c.scalars().all())

    w_start = (now() + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    w_end = w_start + timedelta(hours=6)
    message = request.query_params.get("error")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "Recruiter form",
            "users": users,
            "candidates": candidates,
            "window_start": w_start.isoformat(),
            "window_end": w_end.isoformat(),
            "message": message,
        },
    )


@app.post("/start")
async def ui_start(
    request: Request,
    recruiter_name: str = Form(...),
    recruiter_email: str = Form(...),
    candidate_id: int = Form(...),
    job_title: str = Form(...),
    interviewer_user_ids: list[int] = Form(...),
    window_start: str = Form(...),
    window_end: str = Form(...),
    duration_minutes: int = Form(...),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    tw = TimeWindow(start=_parse_iso(window_start), end=_parse_iso(window_end))

    try:
        r = await start_interview(
            session,
            recruiter_name=recruiter_name,
            recruiter_email=recruiter_email,
            candidate_id=candidate_id,
            job_title=job_title,
            interviewer_user_ids=interviewer_user_ids,
            preferred_window=tw,
            duration_minutes=duration_minutes,
        )
    except ValueError as e:
        return RedirectResponse(url=f"/?error={str(e)}", status_code=303)

    return RedirectResponse(url=f"/interviews/{r.interview.id}", status_code=303)


@app.get("/interviews", response_class=HTMLResponse)
async def ui_interviews(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    res = await session.execute(select(Interview).order_by(Interview.id.desc()))
    interviews = list(res.scalars().all())
    outs = [await _interview_out(session, it) for it in interviews]
    return templates.TemplateResponse(
        "interviews.html",
        {"request": request, "title": "Interviews", "interviews": outs},
    )


@app.get("/proposals", response_class=HTMLResponse)
async def ui_proposals(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    res = await session.execute(select(SchedulingRequest).order_by(SchedulingRequest.id.desc()))
    reqs = list(res.scalars().all())
    return templates.TemplateResponse(
        "proposals.html",
        {"request": request, "title": "Proposals", "proposals": reqs},
    )


@app.get("/proposals/{request_id}", response_class=HTMLResponse)
async def ui_proposal_detail(
    request_id: int, request: Request, session: AsyncSession = Depends(get_session)
) -> Any:
    req = await session.get(SchedulingRequest, request_id)
    if not req:
        raise HTTPException(404, "not found")
    res_opts = await session.execute(
        select(SchedulingOption).where(SchedulingOption.request_id == request_id).order_by(SchedulingOption.start.asc())
    )
    opts = list(res_opts.scalars().all())
    cand = await session.get(Candidate, req.candidate_id)
    return templates.TemplateResponse(
        "proposal_detail.html",
        {"request": request, "title": f"Proposal #{request_id}", "proposal": req, "options": opts, "candidate": cand},
    )


@app.post("/proposals/{request_id}/approve")
async def ui_proposal_approve(
    request_id: int,
    option_id: int = Form(...),
    interviewer_user_ids: list[int] = Form(...),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    try:
        r = await approve_schedule_and_create_interview(
            session,
            request_id=request_id,
            option_id=option_id,
            interviewer_user_ids=interviewer_user_ids,
        )
    except ValueError as e:
        return RedirectResponse(url=f"/proposals/{request_id}?error={str(e)}", status_code=303)

    return RedirectResponse(url=f"/interviews/{r.interview.id}", status_code=303)


@app.get("/interviews/{interview_id}", response_class=HTMLResponse)
async def ui_interview_detail(
    interview_id: int, request: Request, session: AsyncSession = Depends(get_session)
) -> Any:
    interview = await session.get(Interview, interview_id)
    if not interview:
        raise HTTPException(404, "not found")
    out = await _interview_out(session, interview)
    return templates.TemplateResponse(
        "interview_detail.html",
        {"request": request, "title": f"Interview #{interview_id}", "interview": out},
    )


@app.get("/f/{token}", response_class=HTMLResponse)
async def ui_feedback(token: str, request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    candidate_name = "Candidate"
    job_title = "Job"
    try:
        from backend.services.security import parse_feedback_token

        interview_id, _ = parse_feedback_token(token)
        interview = await session.get(Interview, interview_id)
        if interview:
            cand = await session.get(Candidate, interview.candidate_id)
            if cand:
                candidate_name = cand.name
            job_title = interview.job_title
    except Exception:
        pass

    return templates.TemplateResponse(
        "feedback.html",
        {
            "request": request,
            "title": "Feedback",
            "token": token,
            "candidate_name": candidate_name,
            "job_title": job_title,
        },
    )


@app.post("/f/{token}")
async def ui_feedback_submit(
    token: str,
    decision: str = Form(...),
    comment: str = Form(""),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    try:
        await submit_feedback(session, token=token, decision=decision, comment=comment)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse(url="/interviews", status_code=303)


@app.get("/reports/{interview_id}", response_class=HTMLResponse)
async def ui_report(interview_id: int, request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    interview = await session.get(Interview, interview_id)
    if not interview:
        raise HTTPException(404, "not found")
    out = await _interview_out(session, interview)

    res_ats = await session.execute(select(ATSRecord).where(ATSRecord.interview_id == interview.id))
    ats: ATSRecord | None = res_ats.scalar_one_or_none()
    ats_status = ats.status.value if ats else "Unknown"
    recommendation = ats.recommendation.value if (ats and ats.recommendation) else "—"
    updated_at = ats.updated_at.isoformat() if ats else "—"
    summary = ats.summary if ats else None

    return templates.TemplateResponse(
        "report.html",
        {
            "request": request,
            "title": f"Report #{interview_id}",
            "interview": out,
            "ats_status": ats_status,
            "recommendation": recommendation,
            "updated_at": updated_at,
            "summary": summary,
        },
    )

@app.post("/api/interviews/start", response_model=StartInterviewResponse)
async def api_start(req: StartInterviewRequest, session: AsyncSession = Depends(get_session)) -> StartInterviewResponse:
    tw = TimeWindow(start=ensure_aware(req.preferred_window.start), end=ensure_aware(req.preferred_window.end))
    try:
        r = await start_interview(
            session,
            recruiter_name=req.recruiter_name,
            recruiter_email=req.recruiter_email,
            candidate_id=req.candidate_id,
            job_title=req.job_title,
            interviewer_user_ids=req.interviewer_user_ids,
            preferred_window=tw,
            duration_minutes=req.duration_minutes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    out = await _interview_out(session, r.interview)
    return StartInterviewResponse(interview=out)


@app.post("/api/scheduling/propose", response_model=ProposeScheduleResponse)
async def api_propose(
    req: ProposeScheduleRequest, session: AsyncSession = Depends(get_session)
) -> ProposeScheduleResponse:
    tw = TimeWindow(start=ensure_aware(req.preferred_window.start), end=ensure_aware(req.preferred_window.end))
    try:
        r = await propose_schedule(
            session,
            recruiter_name=req.recruiter_name,
            recruiter_email=req.recruiter_email,
            candidate_id=req.candidate_id,
            job_title=req.job_title,
            interviewer_user_ids=req.interviewer_user_ids,
            preferred_window=tw,
            duration_minutes=req.duration_minutes,
            option_limit=req.option_limit,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    return ProposeScheduleResponse(
        request_id=r.request.id,
        options=[SchedulingOptionOut(option_id=o.id, start=o.start, end=o.end) for o in r.options],
    )


@app.post("/api/scheduling/approve", response_model=ApproveScheduleResponse)
async def api_approve(
    req: ApproveScheduleRequest, session: AsyncSession = Depends(get_session)
) -> ApproveScheduleResponse:
    try:
        r = await approve_schedule_and_create_interview(
            session,
            request_id=req.request_id,
            option_id=req.option_id,
            interviewer_user_ids=req.interviewer_user_ids,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    out = await _interview_out(session, r.interview)
    return ApproveScheduleResponse(interview=out)


@app.get("/api/interviews/{interview_id}", response_model=InterviewOut)
async def api_get(interview_id: int, session: AsyncSession = Depends(get_session)) -> InterviewOut:
    interview = await session.get(Interview, interview_id)
    if not interview:
        raise HTTPException(404, "not found")
    return await _interview_out(session, interview)


@app.post("/api/feedback/submit", response_model=SubmitFeedbackResponse)
async def api_submit_feedback(
    req: SubmitFeedbackRequest, session: AsyncSession = Depends(get_session)
) -> SubmitFeedbackResponse:
    try:
        await submit_feedback(session, token=req.token, decision=req.decision, comment=req.comment)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return SubmitFeedbackResponse(ok=True)


@app.get("/api/users", response_model=list[UserOut])
async def api_users(session: AsyncSession = Depends(get_session)) -> list[UserOut]:
    res = await session.execute(select(User).order_by(User.id.asc()))
    users = list(res.scalars().all())
    return [UserOut(id=u.id, name=u.name, email=u.email, role=u.role.value) for u in users]


@app.get("/api/candidates", response_model=list[CandidateOut])
async def api_candidates(session: AsyncSession = Depends(get_session)) -> list[CandidateOut]:
    res = await session.execute(select(Candidate).order_by(Candidate.id.asc()))
    candidates = list(res.scalars().all())
    return [
        CandidateOut(id=c.id, name=c.name, email=c.email, resume_text=c.resume_text) for c in candidates
    ]

