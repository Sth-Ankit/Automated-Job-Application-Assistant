from linkedin_job_assistant.models import ApplicationMode, JobRecord, JobStatus, SearchProfile
from linkedin_job_assistant.services.eligibility import EligibilityService


def test_blacklisted_company_is_skipped() -> None:
    service = EligibilityService()
    profile = SearchProfile(
        name="Backend roles",
        titles=["Software Engineer"],
        company_blacklist=["Bad Corp"],
        application_mode=ApplicationMode.BOTH,
    )
    job = JobRecord(
        linkedin_job_id="1",
        title="Software Engineer",
        company="Bad Corp",
        location="Austin, TX",
        job_url="https://example.com/job",
    )

    decision = service.evaluate(profile, job)

    assert decision.status is JobStatus.SKIPPED
    assert decision.fit_score == 0.0


def test_matching_title_and_keywords_scores_as_qualified() -> None:
    service = EligibilityService()
    profile = SearchProfile(
        name="Frontend roles",
        titles=["Front End Developer"],
        keywords_include=["React", "TypeScript"],
        locations=["Remote"],
    )
    job = JobRecord(
        linkedin_job_id="2",
        title="Front End Developer",
        company="Acme",
        location="Remote",
        job_url="https://example.com/job",
        easy_apply_available=True,
        raw_metadata={"description": "React TypeScript UI work"},
    )

    decision = service.evaluate(profile, job)

    assert decision.status is JobStatus.QUALIFIED
    assert decision.fit_score >= 35
