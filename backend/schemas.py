from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TimeWindowIn(BaseModel):
    start: datetime
    end: datetime


class StartInterviewRequest(BaseModel):
    recruiter_name: str = Field(default="Recruiter")
    recruiter_email: str = Field(default="recruiter@example.com")

    candidate_id: int
    job_title: str
    interviewer_user_ids: list[int]

    preferred_window: TimeWindowIn
    duration_minutes: int = Field(default=60, ge=15, le=240)


class InterviewParticipantOut(BaseModel):
    user_id: int
    name: str
    email: str
    role: str


class InterviewOut(BaseModel):
    id: int
    job_title: str
    status: str
    scheduled_start: datetime
    scheduled_end: datetime
    video_link: str

    recruiter_name: str
    recruiter_email: str

    candidate_id: int
    candidate_name: str
    candidate_email: str

    participants: list[InterviewParticipantOut]
    report_url: str | None = None


class StartInterviewResponse(BaseModel):
    interview: InterviewOut


class SubmitFeedbackRequest(BaseModel):
    token: str
    decision: str  # pass|fail|need_more_info
    comment: str = ""


class SubmitFeedbackResponse(BaseModel):
    ok: bool = True


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str


class CandidateOut(BaseModel):
    id: int
    name: str
    email: str
    resume_text: str


class ProposeScheduleRequest(BaseModel):
    recruiter_name: str = Field(default="Recruiter")
    recruiter_email: str = Field(default="recruiter@example.com")

    candidate_id: int
    job_title: str
    interviewer_user_ids: list[int]

    preferred_window: TimeWindowIn
    duration_minutes: int = Field(default=60, ge=15, le=240)
    option_limit: int = Field(default=3, ge=1, le=5)


class SchedulingOptionOut(BaseModel):
    option_id: int
    start: datetime
    end: datetime


class ProposeScheduleResponse(BaseModel):
    request_id: int
    options: list[SchedulingOptionOut]


class ApproveScheduleRequest(BaseModel):
    request_id: int
    option_id: int
    interviewer_user_ids: list[int]


class ApproveScheduleResponse(BaseModel):
    interview: InterviewOut

