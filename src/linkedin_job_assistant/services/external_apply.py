from __future__ import annotations

from urllib.parse import urlparse

from ..models import ExternalApplyClassification, ExternalApplyStatus


class ExternalApplyService:
    ADAPTERS = {
        "ashbyhq.com": "ashby",
        "bamboohr.com": "bamboohr",
        "greenhouse.io": "greenhouse",
        "greenhouse.com": "greenhouse",
        "icims.com": "icims",
        "jobvite.com": "jobvite",
        "lever.co": "lever",
        "myworkdayjobs.com": "workday",
        "smartrecruiters.com": "smartrecruiters",
        "workday.com": "workday",
    }

    def classify(self, url: str | None) -> ExternalApplyClassification:
        if not url:
            return ExternalApplyClassification(
                status=ExternalApplyStatus.MANUAL_REVIEW,
                adapter_name="none",
                hostname="",
                reason="No external application link is available.",
            )

        hostname = urlparse(url).hostname or ""
        normalized_hostname = hostname.lower()
        for suffix, adapter_name in self.ADAPTERS.items():
            if normalized_hostname.endswith(suffix):
                return ExternalApplyClassification(
                    status=ExternalApplyStatus.SUPPORTED,
                    adapter_name=adapter_name,
                    hostname=normalized_hostname,
                    reason=f"Supported ATS detected: {adapter_name}.",
                )

        if normalized_hostname:
            return ExternalApplyClassification(
                status=ExternalApplyStatus.MANUAL_REVIEW,
                adapter_name="manual_review",
                hostname=normalized_hostname,
                reason="Unknown external application system; assisted handoff required.",
            )

        return ExternalApplyClassification(
            status=ExternalApplyStatus.UNSUPPORTED,
            adapter_name="invalid",
            hostname="",
            reason="Invalid external application URL.",
        )
