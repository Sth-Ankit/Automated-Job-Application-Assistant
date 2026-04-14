from __future__ import annotations

from dataclasses import dataclass
from logging import Logger

from .config import AppPaths
from .database import Database
from .services.apply import ApplyService
from .services.eligibility import EligibilityService
from .services.external_apply import ExternalApplyService
from .services.linkedin_client import LinkedInClient
from .services.messaging import MessagingService
from .services.recruiters import RecruiterFinderService
from .services.runner import AutomationRunner
from .services.search import SearchService


@dataclass(slots=True)
class AppContext:
    paths: AppPaths
    database: Database
    logger: Logger
    client: LinkedInClient
    search_service: SearchService
    eligibility_service: EligibilityService
    external_apply_service: ExternalApplyService
    apply_service: ApplyService
    recruiter_service: RecruiterFinderService
    messaging_service: MessagingService
    runner: AutomationRunner
