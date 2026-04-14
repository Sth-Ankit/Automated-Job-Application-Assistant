from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ApplicationMode(StrEnum):
    EASY_APPLY = "easy_apply"
    EXTERNAL = "external"
    BOTH = "both"


class JobStatus(StrEnum):
    NEW = "new"
    QUALIFIED = "qualified"
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class MessageStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    SENT = "sent"
    FOLLOW_UP_DUE = "follow_up_due"
    RESPONDED = "responded"
    SKIPPED = "skipped"


class ExternalApplyStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    MANUAL_REVIEW = "manual_review"


@dataclass(slots=True)
class SearchProfile:
    name: str
    titles: list[str]
    keywords_include: list[str] = field(default_factory=list)
    keywords_exclude: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    work_modes: list[str] = field(default_factory=list)
    seniority_levels: list[str] = field(default_factory=list)
    company_blacklist: list[str] = field(default_factory=list)
    application_mode: ApplicationMode = ApplicationMode.BOTH
    id: int | None = None


@dataclass(slots=True)
class JobRecord:
    linkedin_job_id: str
    title: str
    company: str
    location: str
    job_url: str
    easy_apply_available: bool = False
    external_apply_url: str | None = None
    status: JobStatus = JobStatus.NEW
    search_profile_id: int | None = None
    fit_score: float = 0.0
    failure_reason: str | None = None
    raw_metadata: dict[str, object] = field(default_factory=dict)
    id: int | None = None


@dataclass(slots=True)
class RecruiterRecord:
    name: str
    title: str
    company: str
    linkedin_profile_url: str
    relationship_to_job: str
    message_status: MessageStatus = MessageStatus.DRAFT
    last_contacted_at: str | None = None
    follow_up_due_at: str | None = None
    shared_skills: list[str] = field(default_factory=list)
    job_id: int | None = None
    id: int | None = None


@dataclass(slots=True)
class MessageTemplate:
    name: str
    stage: str
    content: str
    active: bool = True
    id: int | None = None


@dataclass(slots=True)
class MessageDraft:
    recruiter_id: int
    template_stage: str
    content: str
    status: MessageStatus = MessageStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    id: int | None = None


@dataclass(slots=True)
class ResumeVariant:
    name: str
    file_path: str
    keywords: list[str] = field(default_factory=list)
    search_profile_id: int | None = None
    id: int | None = None


@dataclass(slots=True)
class ScreeningAnswer:
    question_pattern: str
    answer_type: str
    answer_value: str
    id: int | None = None


@dataclass(slots=True)
class ApplicationAttempt:
    job_id: int
    action: str
    status: str
    details: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    id: int | None = None


@dataclass(slots=True)
class AuditLog:
    action: str
    entity_type: str
    entity_id: str
    level: str
    message: str
    payload: dict[str, object] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    id: int | None = None


@dataclass(slots=True)
class ExternalApplyClassification:
    status: ExternalApplyStatus
    adapter_name: str
    hostname: str
    reason: str
