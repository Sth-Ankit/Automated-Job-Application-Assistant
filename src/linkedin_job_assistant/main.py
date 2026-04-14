from __future__ import annotations

import sys

from .app_context import AppContext
from .config import AppPaths
from .database import Database
from .logging_utils import configure_logging
from .models import MessageTemplate
from .services.apply import ApplyService
from .services.eligibility import EligibilityService
from .services.external_apply import ExternalApplyService
from .services.linkedin_client import LinkedInClient
from .services.messaging import MessagingService
from .services.recruiters import RecruiterFinderService
from .services.runner import AutomationRunner
from .services.search import SearchService


def build_context() -> AppContext:
    paths = AppPaths()
    paths.ensure()

    logger = configure_logging(paths.logs_dir)
    database = Database(paths.database_path)
    database.initialize()

    client = LinkedInClient()
    search_service = SearchService(database, client)
    eligibility_service = EligibilityService()
    external_apply_service = ExternalApplyService()
    apply_service = ApplyService(database, client, external_apply_service)
    recruiter_service = RecruiterFinderService(database, client)
    messaging_service = MessagingService()
    runner = AutomationRunner(
        database=database,
        search_service=search_service,
        eligibility_service=eligibility_service,
        apply_service=apply_service,
        recruiter_service=recruiter_service,
        messaging_service=messaging_service,
        logger=logger,
    )

    _seed_defaults(database)

    return AppContext(
        paths=paths,
        database=database,
        logger=logger,
        client=client,
        search_service=search_service,
        eligibility_service=eligibility_service,
        external_apply_service=external_apply_service,
        apply_service=apply_service,
        recruiter_service=recruiter_service,
        messaging_service=messaging_service,
        runner=runner,
    )


def _seed_defaults(database: Database) -> None:
    existing = {template.name for template in database.list_message_templates()}
    legacy_defaults = [
        MessageTemplate(
            name="Default Initial Outreach",
            stage="initial",
            content=(
                "Hi {recruiter_name}, I’m reaching out because I’m interested in {job_title} roles at {company}. "
                "My background lines up with {role} work, and I’d love to stay on your radar for relevant openings."
            ),
        ),
        MessageTemplate(
            name="Default Follow Up 1",
            stage="follow_up_1",
            content=(
                "Hi {recruiter_name}, I wanted to follow up on my note about {job_title} at {company}. "
                "If this role or a similar one is still active, I’d appreciate the chance to connect."
            ),
        ),
        MessageTemplate(
            name="Default Follow Up 2",
            stage="follow_up_2",
            content=(
                "Hi {recruiter_name}, circling back one last time regarding {job_title} opportunities at {company}. "
                "If there is a better person for me to speak with, I’d be grateful for the direction."
            ),
        ),
    ]
    defaults = [
        MessageTemplate(
            name="Default Initial Outreach",
            stage="initial",
            content=(
                "Hi {recruiter_name}, I'm reaching out because I'm interested in {job_title} roles at {company}. "
                "My background lines up with {role} work, and I'd love to stay on your radar for relevant openings."
            ),
        ),
        MessageTemplate(
            name="Default Follow Up 1",
            stage="follow_up_1",
            content=(
                "Hi {recruiter_name}, I wanted to follow up on my note about {job_title} at {company}. "
                "If this role or a similar one is still active, I'd appreciate the chance to connect."
            ),
        ),
        MessageTemplate(
            name="Default Follow Up 2",
            stage="follow_up_2",
            content=(
                "Hi {recruiter_name}, circling back one last time regarding {job_title} opportunities at {company}. "
                "If there is a better person for me to speak with, I'd be grateful for the direction."
            ),
        ),
    ]
    for template in defaults:
        if template.name not in existing:
            database.save_message_template(template)


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError("PySide6 is not installed. Run 'pip install -e .[dev]'.") from exc

    from .ui.main_window import MainWindow

    context = build_context()
    app = QApplication(sys.argv)
    window = MainWindow(context)
    window.show()
    try:
        return app.exec()
    finally:
        context.client.stop()


if __name__ == "__main__":
    raise SystemExit(main())
