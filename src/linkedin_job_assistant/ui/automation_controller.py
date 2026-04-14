from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..config import AppPaths
from ..database import Database
from ..models import JobRecord, ResumeVariant, SearchProfile
from ..services.apply import ApplyService
from ..services.eligibility import EligibilityService
from ..services.external_apply import ExternalApplyService
from ..services.linkedin_client import LinkedInClient
from ..services.messaging import MessagingService
from ..services.recruiters import RecruiterFinderService
from ..services.runner import AutomationRunner
from ..services.search import SearchService


@dataclass(slots=True)
class AutomationBundle:
    client: LinkedInClient
    runner: AutomationRunner


def build_automation_bundle(
    paths: AppPaths,
    database: Database,
    logger: logging.Logger,
    resume_choice_callback: Callable[[JobRecord, list[ResumeVariant]], str | None],
    screening_answer_callback: Callable[[str, str, list[str]], str | None],
) -> AutomationBundle:
    client = LinkedInClient(paths.browser_profile_dir)
    search_service = SearchService(database, client)
    eligibility_service = EligibilityService()
    external_apply_service = ExternalApplyService()
    apply_service = ApplyService(
        database,
        client,
        external_apply_service,
        resume_choice_callback=resume_choice_callback,
        screening_answer_callback=screening_answer_callback,
    )
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
    return AutomationBundle(client=client, runner=runner)


class AutomationWorker(QObject):
    busy_changed = Signal(bool)
    session_opened = Signal()
    search_completed = Signal(int)
    apply_completed = Signal(int, list)
    recruiters_discovered = Signal(int)
    drafts_created = Signal(int, str)
    operation_failed = Signal(str)
    resume_choice_requested = Signal(str, list)
    screening_answer_requested = Signal(str, str, list)

    def __init__(self, paths: AppPaths, database: Database, logger: logging.Logger) -> None:
        super().__init__()
        self._paths = paths
        self._database = database
        self._logger = logger
        self._busy = False
        self._bundle: AutomationBundle | None = None
        self._prompt_event: threading.Event | None = None
        self._prompt_value: str | None = None

    def _set_busy(self, value: bool) -> None:
        if self._busy == value:
            return
        self._busy = value
        self.busy_changed.emit(value)

    def _ensure_bundle(self) -> AutomationBundle:
        if self._bundle is None:
            self._bundle = build_automation_bundle(
                self._paths,
                self._database,
                self._logger,
                self._request_resume_choice,
                self._request_screening_answer,
            )
        return self._bundle

    def _run(self, action: Callable[[], None]) -> None:
        if self._busy:
            self.operation_failed.emit("Another LinkedIn automation task is already running.")
            return
        self._set_busy(True)
        try:
            action()
        except Exception as exc:
            self.operation_failed.emit(str(exc))
        finally:
            self._set_busy(False)

    @Slot()
    def open_session(self) -> None:
        def action() -> None:
            bundle = self._ensure_bundle()
            bundle.runner.open_linkedin_session()
            self.session_opened.emit()

        self._run(action)

    @Slot(int)
    def run_search(self, profile_id: int) -> None:
        def action() -> None:
            bundle = self._ensure_bundle()
            profile = self._database.get_search_profile(profile_id)
            if profile is None:
                raise RuntimeError("Select or save a search profile first.")
            count = bundle.runner.run_search(profile)
            self.search_completed.emit(count)

        self._run(action)

    @Slot(int)
    def discover_recruiters(self, profile_id: int) -> None:
        def action() -> None:
            bundle = self._ensure_bundle()
            profile = self._database.get_search_profile(profile_id)
            if profile is None:
                raise RuntimeError("Select a profile before discovering recruiters.")
            count = bundle.runner.discover_recruiters(profile)
            self.recruiters_discovered.emit(count)

        self._run(action)

    @Slot(int, int)
    def run_apply_cycle(self, _profile_id: int, limit: int) -> None:
        def action() -> None:
            bundle = self._ensure_bundle()
            outcomes = bundle.runner.run_apply_cycle(limit=limit)
            statuses = [outcome.status.value for outcome in outcomes]
            self.apply_completed.emit(len(outcomes), statuses)

        self._run(action)

    @Slot(int, str)
    def draft_messages(self, profile_id: int, stage: str) -> None:
        def action() -> None:
            bundle = self._ensure_bundle()
            profile = self._database.get_search_profile(profile_id)
            if profile is None:
                raise RuntimeError("Select a profile before drafting messages.")
            count = bundle.runner.draft_messages(profile, stage=stage)
            self.drafts_created.emit(count, stage)

        self._run(action)

    @Slot()
    def shutdown(self) -> None:
        if self._bundle is not None:
            self._bundle.client.stop()

    def _request_resume_choice(self, job: JobRecord, variants: list[ResumeVariant]) -> str | None:
        choices = [
            {
                "name": variant.name,
                "file_path": variant.file_path,
                "keywords": ", ".join(variant.keywords),
            }
            for variant in variants
        ]
        return self._wait_for_prompt(
            lambda: self.resume_choice_requested.emit(job.title, choices)
        )

    def _request_screening_answer(self, label: str, answer_type: str, options: list[str]) -> str | None:
        return self._wait_for_prompt(
            lambda: self.screening_answer_requested.emit(label, answer_type, options)
        )

    def _wait_for_prompt(self, emitter: Callable[[], None]) -> str | None:
        self._prompt_event = threading.Event()
        self._prompt_value = None
        emitter()
        self._prompt_event.wait()
        value = self._prompt_value
        self._prompt_event = None
        self._prompt_value = None
        return value

    def provide_prompt_response(self, value: str | None) -> None:
        self._prompt_value = value
        if self._prompt_event is not None:
            self._prompt_event.set()


class AutomationController(QObject):
    busy_changed = Signal(bool)
    session_opened = Signal()
    search_completed = Signal(int)
    apply_completed = Signal(int, list)
    recruiters_discovered = Signal(int)
    drafts_created = Signal(int, str)
    operation_failed = Signal(str)
    resume_choice_requested = Signal(str, list)
    screening_answer_requested = Signal(str, str, list)

    open_session_requested = Signal()
    run_search_requested = Signal(int)
    discover_recruiters_requested = Signal(int)
    run_apply_cycle_requested = Signal(int, int)
    draft_messages_requested = Signal(int, str)
    shutdown_requested = Signal()

    def __init__(self, paths: AppPaths, database: Database, logger: logging.Logger) -> None:
        super().__init__()
        self._thread = QThread()
        self._worker = AutomationWorker(paths, database, logger)
        self._worker.moveToThread(self._thread)

        self.open_session_requested.connect(self._worker.open_session)
        self.run_search_requested.connect(self._worker.run_search)
        self.discover_recruiters_requested.connect(self._worker.discover_recruiters)
        self.run_apply_cycle_requested.connect(self._worker.run_apply_cycle)
        self.draft_messages_requested.connect(self._worker.draft_messages)
        self.shutdown_requested.connect(self._worker.shutdown)

        self._worker.busy_changed.connect(self.busy_changed)
        self._worker.session_opened.connect(self.session_opened)
        self._worker.search_completed.connect(self.search_completed)
        self._worker.apply_completed.connect(self.apply_completed)
        self._worker.recruiters_discovered.connect(self.recruiters_discovered)
        self._worker.drafts_created.connect(self.drafts_created)
        self._worker.operation_failed.connect(self.operation_failed)
        self._worker.resume_choice_requested.connect(self.resume_choice_requested)
        self._worker.screening_answer_requested.connect(self.screening_answer_requested)

        self._thread.start()

    def open_session(self) -> None:
        self.open_session_requested.emit()

    def run_search(self, profile: SearchProfile) -> None:
        if profile.id is None:
            self.operation_failed.emit("Select or save a search profile first.")
            return
        self.run_search_requested.emit(profile.id)

    def discover_recruiters(self, profile: SearchProfile) -> None:
        if profile.id is None:
            self.operation_failed.emit("Select a profile before discovering recruiters.")
            return
        self.discover_recruiters_requested.emit(profile.id)

    def run_apply_cycle(self, limit: int, profile: SearchProfile | None = None) -> None:
        self.run_apply_cycle_requested.emit(profile.id if profile and profile.id else 0, limit)

    def draft_messages(self, profile: SearchProfile, stage: str) -> None:
        if profile.id is None:
            self.operation_failed.emit("Select a profile before drafting messages.")
            return
        self.draft_messages_requested.emit(profile.id, stage)

    def shutdown(self) -> None:
        self.shutdown_requested.emit()
        self._thread.quit()
        self._thread.wait(5000)

    def provide_prompt_response(self, value: str | None) -> None:
        self._worker.provide_prompt_response(value)
