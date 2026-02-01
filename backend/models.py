from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


class UserRole(str, enum.Enum):
    recruiter = "recruiter"
    engineer = "engineer"
    tech_lead = "tech_lead"
    hiring_manager = "hiring_manager"


class InterviewStatus(str, enum.Enum):
    scheduled = "scheduled"
    completed = "completed"
    feedback_requested = "feedback_requested"
    feedback_received = "feedback_received"


class FeedbackDecision(str, enum.Enum):
    pass_ = "pass"
    fail = "fail"
    need_more_info = "need_more_info"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    slack_handle: Mapped[str | None] = mapped_column(String(120), nullable=True)

    calendar_blocks: Mapped[list["CalendarBlock"]] = relationship(back_populates="user")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    resume_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    interviews: Mapped[list["Interview"]] = relationship(back_populates="candidate")


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    recruiter_name: Mapped[str] = mapped_column(String(200), nullable=False, default="Recruiter")
    recruiter_email: Mapped[str] = mapped_column(String(320), nullable=False, default="recruiter@example.com")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    video_link: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus), nullable=False, default=InterviewStatus.scheduled
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    feedback_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consolidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="interviews")
    participants: Mapped[list["InterviewParticipant"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["Feedback"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )
    ats: Mapped["ATSRecord"] = relationship(back_populates="interview", uselist=False)


class InterviewParticipant(Base):
    __tablename__ = "interview_participants"
    __table_args__ = (UniqueConstraint("interview_id", "user_id", name="uq_interview_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    interview: Mapped["Interview"] = relationship(back_populates="participants")
    user: Mapped["User"] = relationship()


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("interview_id", "user_id", name="uq_feedback_interview_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    decision: Mapped[FeedbackDecision] = mapped_column(Enum(FeedbackDecision), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    interview: Mapped["Interview"] = relationship(back_populates="feedback")
    user: Mapped["User"] = relationship()


class ATSStatus(str, enum.Enum):
    interview_scheduled = "Interview Scheduled"
    interview_completed = "Interview Completed"
    feedback_received = "Feedback Received"


class ATSRecommendation(str, enum.Enum):
    hire = "Hire"
    no_hire = "No Hire"
    mixed = "Mixed / Need debrief"
    insufficient_data = "Insufficient data"


class ATSRecord(Base):
    __tablename__ = "ats_records"
    __table_args__ = (UniqueConstraint("interview_id", name="uq_ats_interview"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    status: Mapped[ATSStatus] = mapped_column(Enum(ATSStatus), nullable=False)
    recommendation: Mapped[ATSRecommendation | None] = mapped_column(
        Enum(ATSRecommendation), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    interview: Mapped["Interview"] = relationship(back_populates="ats")


class CalendarBlock(Base):
    __tablename__ = "calendar_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="Busy")

    user: Mapped["User"] = relationship(back_populates="calendar_blocks")


class SchedulingRequestStatus(str, enum.Enum):
    proposed = "proposed"
    approved = "approved"
    cancelled = "cancelled"


class SchedulingRequest(Base):
    __tablename__ = "scheduling_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    recruiter_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recruiter_email: Mapped[str] = mapped_column(String(320), nullable=False)

    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[SchedulingRequestStatus] = mapped_column(
        Enum(SchedulingRequestStatus), nullable=False, default=SchedulingRequestStatus.proposed
    )

    approved_option_id: Mapped[int | None] = mapped_column(ForeignKey("scheduling_options.id"), nullable=True)
    interview_id: Mapped[int | None] = mapped_column(ForeignKey("interviews.id"), nullable=True)

    candidate: Mapped["Candidate"] = relationship()
    options: Mapped[list["SchedulingOption"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        foreign_keys="SchedulingOption.request_id",
    )
    approved_option: Mapped["SchedulingOption | None"] = relationship(
        foreign_keys=[approved_option_id],
        post_update=True,
    )


class SchedulingOption(Base):
    __tablename__ = "scheduling_options"
    __table_args__ = (UniqueConstraint("request_id", "start", "end", name="uq_request_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("scheduling_requests.id"), nullable=False)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    request: Mapped["SchedulingRequest"] = relationship(
        back_populates="options",
        foreign_keys=[request_id],
    )

