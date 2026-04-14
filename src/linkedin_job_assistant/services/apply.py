from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..database import Database
from ..models import ApplicationAttempt, ExternalApplyStatus, JobRecord, JobStatus, ResumeVariant
from .external_apply import ExternalApplyService
from .linkedin_client import LinkedInClient


@dataclass(slots=True)
class ApplyOutcome:
    job: JobRecord
    status: JobStatus
    details: str


class ApplyService:
    def __init__(
        self,
        database: Database,
        client: LinkedInClient,
        external_apply_service: ExternalApplyService,
    ) -> None:
        self.database = database
        self.client = client
        self.external_apply_service = external_apply_service

    def apply_to_job(self, job: JobRecord) -> ApplyOutcome:
        if job.easy_apply_available:
            return self._run_easy_apply(job)
        if job.external_apply_url:
            return self._handle_external_apply(job)
        self.database.update_job_status(job.id or 0, JobStatus.NEEDS_REVIEW, failure_reason="No supported apply path.")
        return ApplyOutcome(job=job, status=JobStatus.NEEDS_REVIEW, details="No apply path detected.")

    def _handle_external_apply(self, job: JobRecord) -> ApplyOutcome:
        classification = self.external_apply_service.classify(job.external_apply_url)
        if classification.status is ExternalApplyStatus.SUPPORTED:
            self.database.update_job_status(job.id or 0, JobStatus.NEEDS_REVIEW, failure_reason=classification.reason)
            self.database.save_application_attempt(
                ApplicationAttempt(
                    job_id=job.id or 0,
                    action=f"external:{classification.adapter_name}",
                    status="manual_review",
                    details=classification.reason,
                )
            )
            return ApplyOutcome(job=job, status=JobStatus.NEEDS_REVIEW, details=classification.reason)

        self.database.update_job_status(job.id or 0, JobStatus.NEEDS_REVIEW, failure_reason=classification.reason)
        return ApplyOutcome(job=job, status=JobStatus.NEEDS_REVIEW, details=classification.reason)

    def _run_easy_apply(self, job: JobRecord) -> ApplyOutcome:
        page = self.client.open_job(job.job_url)
        button = page.locator("button:has-text('Easy Apply')").first
        if button.count() == 0:
            self.database.update_job_status(job.id or 0, JobStatus.NEEDS_REVIEW, failure_reason="Easy Apply button not found.")
            return ApplyOutcome(job=job, status=JobStatus.NEEDS_REVIEW, details="Easy Apply button not found.")

        button.click()
        page.wait_for_timeout(1000)
        for _ in range(8):
            fill_result = self._fill_current_form_step(page, job)
            if fill_result is not None:
                self.database.update_job_status(job.id or 0, JobStatus.NEEDS_REVIEW, failure_reason=fill_result)
                self.database.save_application_attempt(
                    ApplicationAttempt(job_id=job.id or 0, action="easy_apply", status="needs_review", details=fill_result)
                )
                return ApplyOutcome(job=job, status=JobStatus.NEEDS_REVIEW, details=fill_result)

            if self._click_first(page, ["button:has-text('Submit application')", "button[aria-label*='Submit application']"]):
                page.wait_for_timeout(1200)
                self.database.update_job_status(job.id or 0, JobStatus.APPLIED, failure_reason=None)
                self.database.save_application_attempt(
                    ApplicationAttempt(job_id=job.id or 0, action="easy_apply", status="applied", details="Submitted via Easy Apply.")
                )
                return ApplyOutcome(job=job, status=JobStatus.APPLIED, details="Submitted via Easy Apply.")

            if self._click_first(page, ["button:has-text('Review')", "button:has-text('Next')", "button[aria-label='Continue to next step']"]):
                page.wait_for_timeout(900)
                continue

            break

        message = "Easy Apply flow could not be completed automatically."
        self.database.update_job_status(job.id or 0, JobStatus.NEEDS_REVIEW, failure_reason=message)
        self.database.save_application_attempt(
            ApplicationAttempt(job_id=job.id or 0, action="easy_apply", status="needs_review", details=message)
        )
        return ApplyOutcome(job=job, status=JobStatus.NEEDS_REVIEW, details=message)

    def _fill_current_form_step(self, page: Any, job: JobRecord) -> str | None:
        if upload_issue := self._handle_resume_upload(page, job):
            return upload_issue

        text_inputs = page.locator("div[role='dialog'] input").all()
        for input_locator in text_inputs:
            input_type = (input_locator.get_attribute("type") or "text").lower()
            if input_type in {"hidden", "file", "checkbox", "radio"}:
                continue
            label = self._infer_field_label(input_locator)
            answer = self._match_answer(label)
            if answer is None and self._is_required(input_locator):
                return f"Missing screening answer for: {label}"
            if answer is not None:
                input_locator.fill(answer)

        selects = page.locator("div[role='dialog'] select").all()
        for select_locator in selects:
            label = self._infer_field_label(select_locator)
            answer = self._match_answer(label)
            if answer is None:
                if self._is_required(select_locator):
                    return f"Missing selection answer for: {label}"
                continue
            try:
                select_locator.select_option(label=answer)
            except Exception:
                try:
                    select_locator.select_option(answer)
                except Exception:
                    return f"Unable to select answer for: {label}"

        radio_groups = page.locator("fieldset[data-test-form-builder-radio-button-form-component='true']").all()
        for group in radio_groups:
            group_label = self._infer_group_label(group)
            answer = self._match_answer(group_label)
            if answer is None:
                return f"Missing radio answer for: {group_label}"
            option = group.locator(f"label:has-text('{answer}')").first
            if option.count() == 0:
                return f"Configured radio answer not found for: {group_label}"
            option.click()

        return None

    def _handle_resume_upload(self, page: Any, job: JobRecord) -> str | None:
        uploads = page.locator("input[type='file']").all()
        if not uploads:
            return None
        resume = self._select_resume_variant(job)
        if resume is None:
            return "Resume upload required but no matching resume variant is configured."
        if not Path(resume.file_path).exists():
            return f"Resume file does not exist: {resume.file_path}"
        for locator in uploads:
            locator.set_input_files(resume.file_path)
        return None

    def _select_resume_variant(self, job: JobRecord) -> ResumeVariant | None:
        variants = self.database.list_resume_variants()
        if not variants:
            return None
        searchable_text = f"{job.title} {job.company} {job.location} {job.raw_metadata}"
        scored: list[tuple[int, ResumeVariant]] = []
        for variant in variants:
            score = sum(1 for keyword in variant.keywords if keyword.lower() in searchable_text.lower())
            scored.append((score, variant))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    def _match_answer(self, label: str) -> str | None:
        normalized_label = label.lower()
        for answer in self.database.list_screening_answers():
            pattern = answer.question_pattern.strip().lower()
            if not pattern:
                continue
            if pattern in normalized_label or re.search(pattern, normalized_label):
                return answer.answer_value
        return None

    @staticmethod
    def _click_first(page: Any, selectors: list[str]) -> bool:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() == 0:
                    continue
                locator.click()
                return True
            except Exception:
                continue
        return False

    @staticmethod
    def _infer_group_label(group: Any) -> str:
        try:
            legend = group.locator("legend").first
            if legend.count() > 0:
                return (legend.text_content() or "").strip()
        except Exception:
            pass
        return "unknown radio question"

    @staticmethod
    def _infer_field_label(locator: Any) -> str:
        try:
            label_text = locator.evaluate(
                """
                (el) => {
                    if (!el.id) return "";
                    const label = el.ownerDocument.querySelector(`label[for="${el.id}"]`);
                    return label ? label.innerText : "";
                }
                """
            )
            if label_text:
                return str(label_text).strip()
        except Exception:
            pass
        try:
            aria_label = locator.get_attribute("aria-label")
            if aria_label:
                return aria_label.strip()
        except Exception:
            pass
        try:
            placeholder = locator.get_attribute("placeholder")
            if placeholder:
                return placeholder.strip()
        except Exception:
            pass
        return "unknown field"

    @staticmethod
    def _is_required(locator: Any) -> bool:
        try:
            return locator.get_attribute("required") is not None or locator.get_attribute("aria-required") == "true"
        except Exception:
            return False
