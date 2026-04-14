from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

from ..database import Database
from ..models import ApplicationMode, JobRecord, SearchProfile
from .linkedin_client import LinkedInClient


@dataclass(slots=True)
class SearchRunResult:
    profile: SearchProfile
    jobs: list[JobRecord]


class SearchService:
    def __init__(self, database: Database, client: LinkedInClient) -> None:
        self.database = database
        self.client = client

    def build_search_urls(self, profile: SearchProfile) -> list[str]:
        urls: list[str] = []
        location = profile.locations[0] if profile.locations else ""
        for title in profile.titles:
            keywords = quote_plus(title)
            location_query = f"&location={quote_plus(location)}" if location else ""
            apply_filter = "&f_LF=f_AL" if profile.application_mode == ApplicationMode.EASY_APPLY else ""
            urls.append(
                "https://www.linkedin.com/jobs/search/"
                f"?keywords={keywords}{location_query}{apply_filter}"
            )
        return urls

    def run(self, profile: SearchProfile, *, per_title_limit: int = 15) -> SearchRunResult:
        jobs: list[JobRecord] = []
        for url in self.build_search_urls(profile):
            raw_jobs = self.client.fetch_job_cards(url, limit=per_title_limit)
            for raw_job in raw_jobs:
                record = JobRecord(
                    linkedin_job_id=str(raw_job["linkedin_job_id"]),
                    title=str(raw_job["title"]),
                    company=str(raw_job["company"]),
                    location=str(raw_job["location"]),
                    job_url=str(raw_job["job_url"]),
                    easy_apply_available=bool(raw_job["easy_apply_available"]),
                    external_apply_url=raw_job["external_apply_url"],
                    search_profile_id=profile.id,
                    raw_metadata=dict(raw_job.get("raw_metadata", {})),
                )
                self.database.save_job(record)
                jobs.append(record)
        return SearchRunResult(profile=profile, jobs=jobs)
