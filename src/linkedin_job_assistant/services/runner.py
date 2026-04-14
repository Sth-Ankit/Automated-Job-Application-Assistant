from __future__ import annotations

import logging

from ..database import Database
from ..models import AuditLog, JobStatus, MessageStatus, MessageTemplate, SearchProfile
from .apply import ApplyOutcome, ApplyService
from .eligibility import EligibilityService
from .messaging import MessagingService
from .recruiters import RecruiterFinderService
from .search import SearchService


class AutomationRunner:
    def __init__(
        self,
        database: Database,
        search_service: SearchService,
        eligibility_service: EligibilityService,
        apply_service: ApplyService,
        recruiter_service: RecruiterFinderService,
        messaging_service: MessagingService,
        logger: logging.Logger,
    ) -> None:
        self.database = database
        self.search_service = search_service
        self.eligibility_service = eligibility_service
        self.apply_service = apply_service
        self.recruiter_service = recruiter_service
        self.messaging_service = messaging_service
        self.logger = logger

    def open_linkedin_session(self) -> None:
        self.search_service.client.open_login()
        self._audit("session_opened", "session", "linkedin", "info", "Opened LinkedIn login session.")

    def run_search(self, profile: SearchProfile) -> int:
        result = self.search_service.run(profile)
        qualified_count = 0
        for job in result.jobs:
            decision = self.eligibility_service.evaluate(profile, job)
            if job.id is not None:
                self.database.update_job_status(
                    job.id,
                    decision.status,
                    fit_score=decision.fit_score,
                    failure_reason=" | ".join(decision.reasons) if decision.reasons else None,
                )
            if decision.status is JobStatus.QUALIFIED:
                qualified_count += 1
        self._audit(
            "search_completed",
            "search_profile",
            str(profile.id or profile.name),
            "info",
            f"Captured {len(result.jobs)} jobs and qualified {qualified_count}.",
        )
        return len(result.jobs)

    def run_apply_cycle(self, limit: int = 5) -> list[ApplyOutcome]:
        jobs = [job for job in self.database.list_jobs() if job.status is JobStatus.QUALIFIED][:limit]
        outcomes: list[ApplyOutcome] = []
        for job in jobs:
            outcome = self.apply_service.apply_to_job(job)
            outcomes.append(outcome)
            self._audit(
                "apply_attempt",
                "job",
                str(job.id or job.linkedin_job_id),
                "info",
                outcome.details,
                {"status": outcome.status.value},
            )
        return outcomes

    def discover_recruiters(self, profile: SearchProfile, limit_per_job: int = 3) -> int:
        jobs = [job for job in self.database.list_jobs(status=JobStatus.QUALIFIED) if job.search_profile_id == profile.id]
        total = 0
        for job in jobs:
            recruiters = self.recruiter_service.find_for_job(job, profile, limit=limit_per_job)
            total += len(recruiters)
        self._audit(
            "recruiters_discovered",
            "search_profile",
            str(profile.id or profile.name),
            "info",
            f"Discovered {total} recruiters.",
        )
        return total

    def draft_messages(self, profile: SearchProfile, stage: str = "initial") -> int:
        templates = [template for template in self.database.list_message_templates() if template.stage == stage and template.active]
        if not templates:
            raise RuntimeError(f"No active message template found for stage '{stage}'.")
        template = templates[0]

        jobs_by_id = {job.id: job for job in self.database.list_jobs()}
        recruiters = self.database.list_recruiters()
        created = 0
        for recruiter in recruiters:
            if not self.messaging_service.should_contact(recruiter) and stage == "initial":
                continue
            existing_drafts = self.database.list_message_drafts(recruiter.id)
            if any(draft.template_stage == stage for draft in existing_drafts):
                continue
            job = jobs_by_id.get(recruiter.job_id)
            if job is None:
                continue
            bundle = self.messaging_service.build_draft(template, recruiter, job, profile)
            if bundle.draft.recruiter_id == 0 and recruiter.id is not None:
                bundle.draft.recruiter_id = recruiter.id
            self.database.save_message_draft(bundle.draft)
            recruiter.message_status = MessageStatus.READY if stage == "initial" else MessageStatus.FOLLOW_UP_DUE
            recruiter.follow_up_due_at = self.messaging_service.next_follow_up_at()
            self.database.save_recruiter(recruiter)
            created += 1
        self._audit(
            "message_drafts_created",
            "search_profile",
            str(profile.id or profile.name),
            "info",
            f"Created {created} {stage} drafts.",
        )
        return created

    def _audit(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        level: str,
        message: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.logger.info("%s [%s:%s] %s", action, entity_type, entity_id, message)
        self.database.record_audit_log(
            AuditLog(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                level=level,
                message=message,
                payload=payload or {},
            )
        )
