from linkedin_job_assistant.models import ExternalApplyStatus
from linkedin_job_assistant.services.external_apply import ExternalApplyService


def test_supported_ats_is_detected() -> None:
    service = ExternalApplyService()

    result = service.classify("https://boards.greenhouse.io/acme/jobs/123")

    assert result.status is ExternalApplyStatus.SUPPORTED
    assert result.adapter_name == "greenhouse"


def test_unknown_ats_is_sent_to_manual_review() -> None:
    service = ExternalApplyService()

    result = service.classify("https://careers.examplecorp.com/jobs/123")

    assert result.status is ExternalApplyStatus.MANUAL_REVIEW
