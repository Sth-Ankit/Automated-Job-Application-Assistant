from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import (
    ApplicationAttempt,
    ApplicationMode,
    AuditLog,
    JobRecord,
    JobStatus,
    MessageDraft,
    MessageStatus,
    MessageTemplate,
    RecruiterRecord,
    ResumeVariant,
    ScreeningAnswer,
    SearchProfile,
)


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True)


def _load_json(value: str | None, default: object) -> object:
    if not value:
        return default
    return json.loads(value)


class Database:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS search_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    titles_json TEXT NOT NULL,
                    keywords_include_json TEXT NOT NULL,
                    keywords_exclude_json TEXT NOT NULL,
                    locations_json TEXT NOT NULL,
                    work_modes_json TEXT NOT NULL,
                    seniority_levels_json TEXT NOT NULL,
                    company_blacklist_json TEXT NOT NULL,
                    application_mode TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    linkedin_job_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT NOT NULL,
                    job_url TEXT NOT NULL,
                    easy_apply_available INTEGER NOT NULL,
                    external_apply_url TEXT,
                    status TEXT NOT NULL,
                    search_profile_id INTEGER,
                    fit_score REAL NOT NULL,
                    failure_reason TEXT,
                    raw_metadata_json TEXT NOT NULL,
                    FOREIGN KEY(search_profile_id) REFERENCES search_profiles(id)
                );

                CREATE TABLE IF NOT EXISTS recruiters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    linkedin_profile_url TEXT NOT NULL UNIQUE,
                    relationship_to_job TEXT NOT NULL,
                    message_status TEXT NOT NULL,
                    last_contacted_at TEXT,
                    follow_up_due_at TEXT,
                    shared_skills_json TEXT NOT NULL,
                    job_id INTEGER,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE TABLE IF NOT EXISTS message_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    stage TEXT NOT NULL,
                    content TEXT NOT NULL,
                    active INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS message_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recruiter_id INTEGER NOT NULL,
                    template_stage TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(recruiter_id) REFERENCES recruiters(id)
                );

                CREATE TABLE IF NOT EXISTS resume_variants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    file_path TEXT NOT NULL,
                    keywords_json TEXT NOT NULL,
                    search_profile_id INTEGER,
                    FOREIGN KEY(search_profile_id) REFERENCES search_profiles(id)
                );

                CREATE TABLE IF NOT EXISTS screening_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_pattern TEXT NOT NULL UNIQUE,
                    answer_type TEXT NOT NULL,
                    answer_value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS application_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_search_profile(self, profile: SearchProfile) -> SearchProfile:
        values = (
            profile.name,
            _dump_json(profile.titles),
            _dump_json(profile.keywords_include),
            _dump_json(profile.keywords_exclude),
            _dump_json(profile.locations),
            _dump_json(profile.work_modes),
            _dump_json(profile.seniority_levels),
            _dump_json(profile.company_blacklist),
            profile.application_mode.value,
        )
        with self.connect() as connection:
            if profile.id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO search_profiles (
                        name, titles_json, keywords_include_json, keywords_exclude_json,
                        locations_json, work_modes_json, seniority_levels_json,
                        company_blacklist_json, application_mode
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                profile.id = int(cursor.lastrowid)
            else:
                connection.execute(
                    """
                    UPDATE search_profiles
                    SET name = ?, titles_json = ?, keywords_include_json = ?, keywords_exclude_json = ?,
                        locations_json = ?, work_modes_json = ?, seniority_levels_json = ?,
                        company_blacklist_json = ?, application_mode = ?
                    WHERE id = ?
                    """,
                    (*values, profile.id),
                )
        return profile

    def list_search_profiles(self) -> list[SearchProfile]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM search_profiles ORDER BY name").fetchall()
        return [self._row_to_search_profile(row) for row in rows]

    def get_search_profile(self, profile_id: int) -> SearchProfile | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM search_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        return self._row_to_search_profile(row) if row else None

    def save_job(self, job: JobRecord) -> JobRecord:
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM jobs WHERE linkedin_job_id = ?",
                (job.linkedin_job_id,),
            ).fetchone()
            values = (
                job.title,
                job.company,
                job.location,
                job.job_url,
                int(job.easy_apply_available),
                job.external_apply_url,
                job.status.value,
                job.search_profile_id,
                job.fit_score,
                job.failure_reason,
                _dump_json(job.raw_metadata),
                job.linkedin_job_id,
            )
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO jobs (
                        title, company, location, job_url, easy_apply_available,
                        external_apply_url, status, search_profile_id, fit_score,
                        failure_reason, raw_metadata_json, linkedin_job_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                job.id = int(cursor.lastrowid)
            else:
                job.id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE jobs
                    SET title = ?, company = ?, location = ?, job_url = ?, easy_apply_available = ?,
                        external_apply_url = ?, status = ?, search_profile_id = ?, fit_score = ?,
                        failure_reason = ?, raw_metadata_json = ?
                    WHERE linkedin_job_id = ?
                    """,
                    values,
                )
        return job

    def list_jobs(self, *, status: JobStatus | None = None) -> list[JobRecord]:
        query = "SELECT * FROM jobs"
        params: tuple[object, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status.value,)
        query += " ORDER BY fit_score DESC, id DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def get_job(self, job_id: int) -> JobRecord | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def update_job_status(
        self,
        job_id: int,
        status: JobStatus,
        *,
        fit_score: float | None = None,
        failure_reason: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, fit_score = COALESCE(?, fit_score), failure_reason = ?
                WHERE id = ?
                """,
                (status.value, fit_score, failure_reason, job_id),
            )

    def save_recruiter(self, recruiter: RecruiterRecord) -> RecruiterRecord:
        values = (
            recruiter.name,
            recruiter.title,
            recruiter.company,
            recruiter.relationship_to_job,
            recruiter.message_status.value,
            recruiter.last_contacted_at,
            recruiter.follow_up_due_at,
            _dump_json(recruiter.shared_skills),
            recruiter.job_id,
            recruiter.linkedin_profile_url,
        )
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM recruiters WHERE linkedin_profile_url = ?",
                (recruiter.linkedin_profile_url,),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO recruiters (
                        name, title, company, relationship_to_job, message_status,
                        last_contacted_at, follow_up_due_at, shared_skills_json, job_id,
                        linkedin_profile_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                recruiter.id = int(cursor.lastrowid)
            else:
                recruiter.id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE recruiters
                    SET name = ?, title = ?, company = ?, relationship_to_job = ?, message_status = ?,
                        last_contacted_at = ?, follow_up_due_at = ?, shared_skills_json = ?, job_id = ?
                    WHERE linkedin_profile_url = ?
                    """,
                    values,
                )
        return recruiter

    def list_recruiters(self) -> list[RecruiterRecord]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM recruiters ORDER BY id DESC").fetchall()
        return [self._row_to_recruiter(row) for row in rows]

    def save_message_template(self, template: MessageTemplate) -> MessageTemplate:
        with self.connect() as connection:
            if template.id is None:
                existing = connection.execute(
                    "SELECT id FROM message_templates WHERE name = ?",
                    (template.name,),
                ).fetchone()
                if existing is not None:
                    template.id = int(existing["id"])
            if template.id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO message_templates (name, stage, content, active)
                    VALUES (?, ?, ?, ?)
                    """,
                    (template.name, template.stage, template.content, int(template.active)),
                )
                template.id = int(cursor.lastrowid)
            else:
                connection.execute(
                    """
                    UPDATE message_templates
                    SET name = ?, stage = ?, content = ?, active = ?
                    WHERE id = ?
                    """,
                    (template.name, template.stage, template.content, int(template.active), template.id),
                )
        return template

    def list_message_templates(self) -> list[MessageTemplate]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM message_templates ORDER BY stage, name"
            ).fetchall()
        return [self._row_to_message_template(row) for row in rows]

    def save_message_draft(self, draft: MessageDraft) -> MessageDraft:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO message_drafts (recruiter_id, template_stage, content, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    draft.recruiter_id,
                    draft.template_stage,
                    draft.content,
                    draft.status.value,
                    draft.created_at,
                ),
            )
            draft.id = int(cursor.lastrowid)
        return draft

    def list_message_drafts(self, recruiter_id: int | None = None) -> list[MessageDraft]:
        query = "SELECT * FROM message_drafts"
        params: tuple[object, ...] = ()
        if recruiter_id is not None:
            query += " WHERE recruiter_id = ?"
            params = (recruiter_id,)
        query += " ORDER BY id DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_message_draft(row) for row in rows]

    def save_resume_variant(self, variant: ResumeVariant) -> ResumeVariant:
        with self.connect() as connection:
            if variant.id is None:
                existing = connection.execute(
                    "SELECT id FROM resume_variants WHERE name = ?",
                    (variant.name,),
                ).fetchone()
                if existing is not None:
                    variant.id = int(existing["id"])
            if variant.id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO resume_variants (name, file_path, keywords_json, search_profile_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        variant.name,
                        variant.file_path,
                        _dump_json(variant.keywords),
                        variant.search_profile_id,
                    ),
                )
                variant.id = int(cursor.lastrowid)
            else:
                connection.execute(
                    """
                    UPDATE resume_variants
                    SET name = ?, file_path = ?, keywords_json = ?, search_profile_id = ?
                    WHERE id = ?
                    """,
                    (
                        variant.name,
                        variant.file_path,
                        _dump_json(variant.keywords),
                        variant.search_profile_id,
                        variant.id,
                    ),
                )
        return variant

    def list_resume_variants(self) -> list[ResumeVariant]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM resume_variants ORDER BY name").fetchall()
        return [self._row_to_resume_variant(row) for row in rows]

    def save_screening_answer(self, answer: ScreeningAnswer) -> ScreeningAnswer:
        with self.connect() as connection:
            if answer.id is None:
                existing = connection.execute(
                    "SELECT id FROM screening_answers WHERE question_pattern = ?",
                    (answer.question_pattern,),
                ).fetchone()
                if existing is not None:
                    answer.id = int(existing["id"])
            if answer.id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO screening_answers (question_pattern, answer_type, answer_value)
                    VALUES (?, ?, ?)
                    """,
                    (answer.question_pattern, answer.answer_type, answer.answer_value),
                )
                answer.id = int(cursor.lastrowid)
            else:
                connection.execute(
                    """
                    UPDATE screening_answers
                    SET question_pattern = ?, answer_type = ?, answer_value = ?
                    WHERE id = ?
                    """,
                    (answer.question_pattern, answer.answer_type, answer.answer_value, answer.id),
                )
        return answer

    def list_screening_answers(self) -> list[ScreeningAnswer]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM screening_answers ORDER BY question_pattern"
            ).fetchall()
        return [self._row_to_screening_answer(row) for row in rows]

    def save_application_attempt(self, attempt: ApplicationAttempt) -> ApplicationAttempt:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO application_attempts (job_id, action, status, details, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (attempt.job_id, attempt.action, attempt.status, attempt.details, attempt.created_at),
            )
            attempt.id = int(cursor.lastrowid)
        return attempt

    def list_application_attempts(self, job_id: int | None = None) -> list[ApplicationAttempt]:
        query = "SELECT * FROM application_attempts"
        params: tuple[object, ...] = ()
        if job_id is not None:
            query += " WHERE job_id = ?"
            params = (job_id,)
        query += " ORDER BY id DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_application_attempt(row) for row in rows]

    def record_audit_log(self, entry: AuditLog) -> AuditLog:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_logs (action, entity_type, entity_id, level, message, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.action,
                    entry.entity_type,
                    entry.entity_id,
                    entry.level,
                    entry.message,
                    _dump_json(entry.payload),
                    entry.created_at,
                ),
            )
            entry.id = int(cursor.lastrowid)
        return entry

    def list_audit_logs(self, limit: int = 100) -> list[AuditLog]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_audit_log(row) for row in rows]

    @staticmethod
    def _row_to_search_profile(row: sqlite3.Row) -> SearchProfile:
        return SearchProfile(
            id=row["id"],
            name=row["name"],
            titles=list(_load_json(row["titles_json"], [])),
            keywords_include=list(_load_json(row["keywords_include_json"], [])),
            keywords_exclude=list(_load_json(row["keywords_exclude_json"], [])),
            locations=list(_load_json(row["locations_json"], [])),
            work_modes=list(_load_json(row["work_modes_json"], [])),
            seniority_levels=list(_load_json(row["seniority_levels_json"], [])),
            company_blacklist=list(_load_json(row["company_blacklist_json"], [])),
            application_mode=ApplicationMode(row["application_mode"]),
        )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            linkedin_job_id=row["linkedin_job_id"],
            title=row["title"],
            company=row["company"],
            location=row["location"],
            job_url=row["job_url"],
            easy_apply_available=bool(row["easy_apply_available"]),
            external_apply_url=row["external_apply_url"],
            status=JobStatus(row["status"]),
            search_profile_id=row["search_profile_id"],
            fit_score=row["fit_score"],
            failure_reason=row["failure_reason"],
            raw_metadata=dict(_load_json(row["raw_metadata_json"], {})),
        )

    @staticmethod
    def _row_to_recruiter(row: sqlite3.Row) -> RecruiterRecord:
        return RecruiterRecord(
            id=row["id"],
            name=row["name"],
            title=row["title"],
            company=row["company"],
            linkedin_profile_url=row["linkedin_profile_url"],
            relationship_to_job=row["relationship_to_job"],
            message_status=MessageStatus(row["message_status"]),
            last_contacted_at=row["last_contacted_at"],
            follow_up_due_at=row["follow_up_due_at"],
            shared_skills=list(_load_json(row["shared_skills_json"], [])),
            job_id=row["job_id"],
        )

    @staticmethod
    def _row_to_message_template(row: sqlite3.Row) -> MessageTemplate:
        return MessageTemplate(
            id=row["id"],
            name=row["name"],
            stage=row["stage"],
            content=row["content"],
            active=bool(row["active"]),
        )

    @staticmethod
    def _row_to_message_draft(row: sqlite3.Row) -> MessageDraft:
        return MessageDraft(
            id=row["id"],
            recruiter_id=row["recruiter_id"],
            template_stage=row["template_stage"],
            content=row["content"],
            status=MessageStatus(row["status"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_resume_variant(row: sqlite3.Row) -> ResumeVariant:
        return ResumeVariant(
            id=row["id"],
            name=row["name"],
            file_path=row["file_path"],
            keywords=list(_load_json(row["keywords_json"], [])),
            search_profile_id=row["search_profile_id"],
        )

    @staticmethod
    def _row_to_screening_answer(row: sqlite3.Row) -> ScreeningAnswer:
        return ScreeningAnswer(
            id=row["id"],
            question_pattern=row["question_pattern"],
            answer_type=row["answer_type"],
            answer_value=row["answer_value"],
        )

    @staticmethod
    def _row_to_application_attempt(row: sqlite3.Row) -> ApplicationAttempt:
        return ApplicationAttempt(
            id=row["id"],
            job_id=row["job_id"],
            action=row["action"],
            status=row["status"],
            details=row["details"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_audit_log(row: sqlite3.Row) -> AuditLog:
        return AuditLog(
            id=row["id"],
            action=row["action"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            level=row["level"],
            message=row["message"],
            payload=dict(_load_json(row["payload_json"], {})),
            created_at=row["created_at"],
        )
