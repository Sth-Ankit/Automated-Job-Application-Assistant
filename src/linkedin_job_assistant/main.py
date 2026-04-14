from __future__ import annotations

import sys
from pathlib import Path

from .app_context import AppContext
from .config import AppPaths
from .database import Database
from .logging_utils import configure_logging
from .models import MessageTemplate, ResumeVariant
from .ui.automation_controller import AutomationController


def build_context() -> AppContext:
    paths = AppPaths()
    paths.ensure()

    logger = configure_logging(paths.logs_dir)
    database = Database(paths.database_path)
    database.initialize()
    automation_controller = AutomationController(paths, database, logger)

    _seed_defaults(database)

    return AppContext(
        paths=paths,
        database=database,
        logger=logger,
        automation_controller=automation_controller,
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

    resume_path = Path(r"C:\Users\shres\OneDrive\Desktop\CurrentResume\Resume - Ankit Shrestha 2026.pdf")
    if resume_path.exists():
        database.save_resume_variant(
            ResumeVariant(
                name="Ankit Shrestha 2026",
                file_path=str(resume_path),
                keywords=["software engineer", "full stack", "frontend", "java", "python", "react"],
            )
        )


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError("PySide6 is not installed. Run 'pip install -e .[dev]'.") from exc

    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    context = build_context()
    window = MainWindow(context)
    window.show()
    try:
        return app.exec()
    finally:
        context.automation_controller.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
