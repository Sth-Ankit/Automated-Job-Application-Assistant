from __future__ import annotations

from ..database import Database
from ..models import JobRecord, RecruiterRecord, SearchProfile
from .linkedin_client import LinkedInClient


class RecruiterFinderService:
    def __init__(self, database: Database, client: LinkedInClient) -> None:
        self.database = database
        self.client = client

    def find_for_job(self, job: JobRecord, profile: SearchProfile, *, limit: int = 5) -> list[RecruiterRecord]:
        raw_recruiters = self.client.find_recruiters(job.company, job.title, limit=limit)
        recruiters: list[RecruiterRecord] = []
        for raw in raw_recruiters:
            shared_skills = [
                keyword
                for keyword in profile.keywords_include
                if keyword.lower() in f"{job.title} {job.company}".lower()
            ]
            recruiter = RecruiterRecord(
                name=str(raw["name"]),
                title=str(raw["title"]),
                company=job.company,
                linkedin_profile_url=str(raw["linkedin_profile_url"]),
                relationship_to_job=f"Recruiter for {job.title}",
                shared_skills=shared_skills,
                job_id=job.id,
            )
            self.database.save_recruiter(recruiter)
            recruiters.append(recruiter)
        return recruiters
