from linkedin_job_assistant.models import JobRecord, MessageTemplate, RecruiterRecord, SearchProfile
from linkedin_job_assistant.services.messaging import MessagingService


def test_render_template_populates_tokens() -> None:
    service = MessagingService()
    template = MessageTemplate(
        name="initial",
        stage="initial",
        content="Hi {recruiter_name}, I am interested in {job_title} at {company}. Skills: {shared_skills}",
    )
    recruiter = RecruiterRecord(
        name="Jordan",
        title="Technical Recruiter",
        company="Acme",
        linkedin_profile_url="https://linkedin.com/in/jordan",
        relationship_to_job="Recruiter for Front End Developer",
        shared_skills=["React", "TypeScript"],
        id=7,
    )
    job = JobRecord(
        linkedin_job_id="9",
        title="Front End Developer",
        company="Acme",
        location="Remote",
        job_url="https://example.com/job",
    )
    profile = SearchProfile(name="Frontend", titles=["Front End Developer"])

    rendered = service.render_template(template, recruiter, job, profile)

    assert "Jordan" in rendered
    assert "Front End Developer" in rendered
    assert "Acme" in rendered
    assert "React, TypeScript" in rendered
