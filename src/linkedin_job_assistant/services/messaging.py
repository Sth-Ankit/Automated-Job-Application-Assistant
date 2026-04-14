from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models import JobRecord, MessageDraft, MessageTemplate, RecruiterRecord, SearchProfile


class SafeFormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


@dataclass(slots=True)
class DraftBundle:
    recruiter: RecruiterRecord
    template: MessageTemplate
    draft: MessageDraft


class MessagingService:
    def __init__(self, cooldown_days: int = 14, follow_up_days: int = 7) -> None:
        self.cooldown_days = cooldown_days
        self.follow_up_days = follow_up_days

    def render_template(
        self,
        template: MessageTemplate,
        recruiter: RecruiterRecord,
        job: JobRecord,
        profile: SearchProfile,
    ) -> str:
        shared_skills = ", ".join(recruiter.shared_skills)
        tokens = SafeFormatDict(
            recruiter_name=recruiter.name,
            company=recruiter.company,
            role=profile.titles[0] if profile.titles else job.title,
            job_title=job.title,
            shared_skills=shared_skills,
            location=job.location,
        )
        return template.content.format_map(tokens).strip()

    def should_contact(self, recruiter: RecruiterRecord) -> bool:
        if not recruiter.last_contacted_at:
            return True
        last_contact = datetime.fromisoformat(recruiter.last_contacted_at)
        return datetime.utcnow() - last_contact >= timedelta(days=self.cooldown_days)

    def next_follow_up_at(self) -> str:
        return (datetime.utcnow() + timedelta(days=self.follow_up_days)).isoformat()

    def build_draft(
        self,
        template: MessageTemplate,
        recruiter: RecruiterRecord,
        job: JobRecord,
        profile: SearchProfile,
    ) -> DraftBundle:
        content = self.render_template(template, recruiter, job, profile)
        draft = MessageDraft(
            recruiter_id=recruiter.id or 0,
            template_stage=template.stage,
            content=content,
        )
        return DraftBundle(recruiter=recruiter, template=template, draft=draft)
