from __future__ import annotations

from dataclasses import dataclass, field

from ..models import ApplicationMode, JobRecord, JobStatus, SearchProfile


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _contains_any(text: str, needles: list[str]) -> bool:
    haystack = _normalize(text)
    return any(_normalize(needle) in haystack for needle in needles if needle.strip())


@dataclass(slots=True)
class QualificationDecision:
    fit_score: float
    status: JobStatus
    reasons: list[str] = field(default_factory=list)


class EligibilityService:
    def evaluate(self, profile: SearchProfile, job: JobRecord) -> QualificationDecision:
        reasons: list[str] = []
        score = 0.0

        searchable_text = " ".join(
            [
                job.title,
                job.company,
                job.location,
                str(job.raw_metadata.get("description", "")),
                str(job.raw_metadata.get("snippet", "")),
            ]
        )
        normalized_text = _normalize(searchable_text)

        if _contains_any(job.company, profile.company_blacklist):
            return QualificationDecision(
                fit_score=0.0,
                status=JobStatus.SKIPPED,
                reasons=["Company is on the blacklist."],
            )

        if _contains_any(normalized_text, profile.keywords_exclude):
            return QualificationDecision(
                fit_score=0.0,
                status=JobStatus.SKIPPED,
                reasons=["Excluded keyword matched the posting."],
            )

        if profile.titles and _contains_any(job.title, profile.titles):
            score += 45
            reasons.append("Job title matches a target title.")
        elif profile.titles:
            score -= 25
            reasons.append("Job title does not match the target titles closely.")

        include_hits = [term for term in profile.keywords_include if _normalize(term) in normalized_text]
        if include_hits:
            score += min(len(include_hits) * 12, 30)
            reasons.append(f"Matched include keywords: {', '.join(include_hits[:3])}.")

        if profile.locations:
            if _contains_any(job.location, profile.locations):
                score += 10
                reasons.append("Location matches the search profile.")
            else:
                score -= 10
                reasons.append("Location is outside the preferred set.")

        if profile.work_modes and _contains_any(normalized_text, profile.work_modes):
            score += 8
            reasons.append("Work mode appears compatible.")

        if profile.seniority_levels and _contains_any(normalized_text, profile.seniority_levels):
            score += 8
            reasons.append("Seniority level looks compatible.")

        if profile.application_mode == ApplicationMode.EASY_APPLY and not job.easy_apply_available:
            return QualificationDecision(
                fit_score=max(score, 0.0),
                status=JobStatus.SKIPPED,
                reasons=reasons + ["Profile is limited to Easy Apply jobs."],
            )

        if profile.application_mode == ApplicationMode.EXTERNAL and not job.external_apply_url:
            return QualificationDecision(
                fit_score=max(score, 0.0),
                status=JobStatus.SKIPPED,
                reasons=reasons + ["Profile is limited to external applications."],
            )

        final_score = max(min(score, 100.0), 0.0)
        status = JobStatus.QUALIFIED if final_score >= 35 else JobStatus.NEEDS_REVIEW
        if status is JobStatus.NEEDS_REVIEW:
            reasons.append("Posting needs manual review before applying.")
        return QualificationDecision(fit_score=final_score, status=status, reasons=reasons)
