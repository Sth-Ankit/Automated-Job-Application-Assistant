from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..app_context import AppContext
from ..models import ApplicationMode, MessageTemplate, ResumeVariant, ScreeningAnswer, SearchProfile


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("LinkedIn Job Assistant")
        self.resize(1440, 900)
        self.setStatusBar(QStatusBar())

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self._on_profile_selected)

        self.job_table = self._create_job_table()
        self.queue_table = self._create_job_table()
        self.recruiter_table = self._create_recruiter_table()
        self.draft_preview = QPlainTextEdit()
        self.draft_preview.setReadOnly(True)
        self.activity_log = QPlainTextEdit()
        self.activity_log.setReadOnly(True)

        self._build_job_search_tab()
        self._build_application_tab()
        self._build_recruiter_tab()
        self._build_templates_tab()

        self.refresh_all()

    def _build_job_search_tab(self) -> None:
        tab = QWidget()
        layout = QHBoxLayout(tab)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Saved Search Profiles"))
        left_layout.addWidget(self.profile_list)

        form_group = QGroupBox("Search Profile")
        form_layout = QFormLayout(form_group)
        self.profile_name = QLineEdit()
        self.profile_titles = QTextEdit()
        self.profile_titles.setFixedHeight(70)
        self.profile_keywords_include = QLineEdit()
        self.profile_keywords_exclude = QLineEdit()
        self.profile_locations = QLineEdit()
        self.profile_work_modes = QLineEdit()
        self.profile_seniority = QLineEdit()
        self.profile_blacklist = QTextEdit()
        self.profile_blacklist.setFixedHeight(60)
        self.profile_application_mode = QComboBox()
        self.profile_application_mode.addItems(
            [ApplicationMode.BOTH.value, ApplicationMode.EASY_APPLY.value, ApplicationMode.EXTERNAL.value]
        )
        form_layout.addRow("Name", self.profile_name)
        form_layout.addRow("Titles (comma/new line)", self.profile_titles)
        form_layout.addRow("Include keywords", self.profile_keywords_include)
        form_layout.addRow("Exclude keywords", self.profile_keywords_exclude)
        form_layout.addRow("Locations", self.profile_locations)
        form_layout.addRow("Work modes", self.profile_work_modes)
        form_layout.addRow("Seniority", self.profile_seniority)
        form_layout.addRow("Company blacklist", self.profile_blacklist)
        form_layout.addRow("Application mode", self.profile_application_mode)
        left_layout.addWidget(form_group)

        button_row = QHBoxLayout()
        save_button = QPushButton("Save Profile")
        save_button.clicked.connect(self.save_profile)
        session_button = QPushButton("Open LinkedIn Session")
        session_button.clicked.connect(self.open_linkedin_session)
        search_button = QPushButton("Run Search")
        search_button.clicked.connect(self.run_search)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_all)
        for button in (save_button, session_button, search_button, refresh_button):
            button_row.addWidget(button)
        left_layout.addLayout(button_row)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Jobs"))
        right_layout.addWidget(self.job_table)

        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        self.tabs.addTab(tab, "Job Search")

    def _build_application_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        controls = QHBoxLayout()
        refresh_button = QPushButton("Refresh Queue")
        refresh_button.clicked.connect(self.refresh_jobs)
        apply_button = QPushButton("Run Apply Cycle")
        apply_button.clicked.connect(self.run_apply_cycle)
        self.apply_limit = QSpinBox()
        self.apply_limit.setRange(1, 100)
        self.apply_limit.setValue(5)
        controls.addWidget(refresh_button)
        controls.addWidget(QLabel("Max jobs"))
        controls.addWidget(self.apply_limit)
        controls.addWidget(apply_button)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(self.queue_table)

        self.tabs.addTab(tab, "Application Queue")

    def _build_recruiter_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        controls = QHBoxLayout()
        refresh_button = QPushButton("Refresh Recruiters")
        refresh_button.clicked.connect(self.refresh_recruiters)
        find_button = QPushButton("Find Recruiters")
        find_button.clicked.connect(self.discover_recruiters)
        draft_initial = QPushButton("Draft Initial Messages")
        draft_initial.clicked.connect(lambda: self.draft_messages("initial"))
        draft_follow_up = QPushButton("Draft Follow Up 1")
        draft_follow_up.clicked.connect(lambda: self.draft_messages("follow_up_1"))
        controls.addWidget(refresh_button)
        controls.addWidget(find_button)
        controls.addWidget(draft_initial)
        controls.addWidget(draft_follow_up)
        controls.addStretch()
        layout.addLayout(controls)

        splitter = QSplitter()
        splitter.addWidget(self.recruiter_table)
        splitter.addWidget(self.draft_preview)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)
        self.recruiter_table.itemSelectionChanged.connect(self.show_selected_recruiter_draft)

        self.tabs.addTab(tab, "Recruiter Outreach")

    def _build_templates_tab(self) -> None:
        tab = QWidget()
        layout = QGridLayout(tab)

        template_group = QGroupBox("Message Template")
        template_form = QFormLayout(template_group)
        self.template_name = QLineEdit()
        self.template_stage = QComboBox()
        self.template_stage.addItems(["initial", "follow_up_1", "follow_up_2"])
        self.template_content = QTextEdit()
        self.template_content.setFixedHeight(180)
        self.template_active = QCheckBox("Active")
        self.template_active.setChecked(True)
        template_save = QPushButton("Save Template")
        template_save.clicked.connect(self.save_template)
        template_form.addRow("Name", self.template_name)
        template_form.addRow("Stage", self.template_stage)
        template_form.addRow("Content", self.template_content)
        template_form.addRow("", self.template_active)
        template_form.addRow("", template_save)

        resume_group = QGroupBox("Resume Variant")
        resume_form = QFormLayout(resume_group)
        self.resume_name = QLineEdit()
        self.resume_path = QLineEdit()
        self.resume_keywords = QLineEdit()
        resume_save = QPushButton("Save Resume Variant")
        resume_save.clicked.connect(self.save_resume_variant)
        resume_form.addRow("Name", self.resume_name)
        resume_form.addRow("File path", self.resume_path)
        resume_form.addRow("Keywords", self.resume_keywords)
        resume_form.addRow("", resume_save)

        answer_group = QGroupBox("Screening Answer")
        answer_form = QFormLayout(answer_group)
        self.answer_pattern = QLineEdit()
        self.answer_type = QComboBox()
        self.answer_type.addItems(["text", "select", "radio"])
        self.answer_value = QLineEdit()
        answer_save = QPushButton("Save Screening Answer")
        answer_save.clicked.connect(self.save_screening_answer)
        answer_form.addRow("Question pattern", self.answer_pattern)
        answer_form.addRow("Answer type", self.answer_type)
        answer_form.addRow("Answer value", self.answer_value)
        answer_form.addRow("", answer_save)

        activity_group = QGroupBox("Activity Log")
        activity_layout = QVBoxLayout(activity_group)
        refresh_logs = QPushButton("Refresh Activity")
        refresh_logs.clicked.connect(self.refresh_activity)
        activity_layout.addWidget(refresh_logs)
        activity_layout.addWidget(self.activity_log)

        layout.addWidget(template_group, 0, 0)
        layout.addWidget(resume_group, 0, 1)
        layout.addWidget(answer_group, 1, 0)
        layout.addWidget(activity_group, 1, 1)
        self.tabs.addTab(tab, "Templates / Settings")

    def _create_job_table(self) -> QTableWidget:
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(["ID", "Title", "Company", "Location", "Status", "Score", "Apply Path"])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _create_recruiter_table(self) -> QTableWidget:
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["ID", "Name", "Title", "Company", "Status", "LinkedIn URL"])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def refresh_all(self) -> None:
        self.refresh_profiles()
        self.refresh_jobs()
        self.refresh_recruiters()
        self.refresh_activity()

    def refresh_profiles(self) -> None:
        current_id = self.selected_profile_id()
        self.profile_list.clear()
        for profile in self.context.database.list_search_profiles():
            item = QListWidgetItem(profile.name)
            item.setData(Qt.ItemDataRole.UserRole, profile.id)
            self.profile_list.addItem(item)
            if profile.id == current_id:
                self.profile_list.setCurrentItem(item)

    def refresh_jobs(self) -> None:
        jobs = self.context.database.list_jobs()
        self._populate_job_table(self.job_table, jobs)
        self._populate_job_table(self.queue_table, jobs)

    def refresh_recruiters(self) -> None:
        recruiters = self.context.database.list_recruiters()
        self.recruiter_table.setRowCount(len(recruiters))
        for row, recruiter in enumerate(recruiters):
            values = [
                str(recruiter.id or ""),
                recruiter.name,
                recruiter.title,
                recruiter.company,
                recruiter.message_status.value,
                recruiter.linkedin_profile_url,
            ]
            for column, value in enumerate(values):
                self.recruiter_table.setItem(row, column, QTableWidgetItem(value))
        self.recruiter_table.resizeColumnsToContents()

    def refresh_activity(self) -> None:
        lines = []
        for entry in self.context.database.list_audit_logs(limit=50):
            lines.append(f"{entry.created_at} [{entry.level}] {entry.action}: {entry.message}")
        self.activity_log.setPlainText("\n".join(lines))

    def selected_profile_id(self) -> int | None:
        item = self.profile_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def selected_profile(self) -> SearchProfile | None:
        profile_id = self.selected_profile_id()
        if profile_id is None:
            return None
        return self.context.database.get_search_profile(profile_id)

    def save_profile(self) -> None:
        profile = SearchProfile(
            id=self.selected_profile_id(),
            name=self.profile_name.text().strip(),
            titles=_csv(self.profile_titles.toPlainText()),
            keywords_include=_csv(self.profile_keywords_include.text()),
            keywords_exclude=_csv(self.profile_keywords_exclude.text()),
            locations=_csv(self.profile_locations.text()),
            work_modes=_csv(self.profile_work_modes.text()),
            seniority_levels=_csv(self.profile_seniority.text()),
            company_blacklist=_csv(self.profile_blacklist.toPlainText()),
            application_mode=ApplicationMode(self.profile_application_mode.currentText()),
        )
        if not profile.name or not profile.titles:
            self._error("Profile name and at least one title are required.")
            return
        self.context.database.save_search_profile(profile)
        self.refresh_profiles()
        self.statusBar().showMessage(f"Saved profile '{profile.name}'.", 5000)

    def open_linkedin_session(self) -> None:
        try:
            self.context.runner.open_linkedin_session()
        except Exception as exc:
            self._error(str(exc))
            return
        QMessageBox.information(
            self,
            "Manual Login",
            "A browser window was opened. Log into LinkedIn there, then come back and run search or apply actions.",
        )
        self.refresh_activity()

    def run_search(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            self._error("Select or save a search profile first.")
            return
        try:
            count = self.context.runner.run_search(profile)
        except Exception as exc:
            self._error(str(exc))
            return
        self.refresh_jobs()
        self.refresh_activity()
        self.statusBar().showMessage(f"Search captured {count} jobs.", 5000)

    def run_apply_cycle(self) -> None:
        try:
            outcomes = self.context.runner.run_apply_cycle(limit=self.apply_limit.value())
        except Exception as exc:
            self._error(str(exc))
            return
        self.refresh_jobs()
        self.refresh_activity()
        self.statusBar().showMessage(f"Processed {len(outcomes)} application attempts.", 5000)

    def discover_recruiters(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            self._error("Select a profile before discovering recruiters.")
            return
        try:
            count = self.context.runner.discover_recruiters(profile)
        except Exception as exc:
            self._error(str(exc))
            return
        self.refresh_recruiters()
        self.refresh_activity()
        self.statusBar().showMessage(f"Discovered {count} recruiters.", 5000)

    def draft_messages(self, stage: str) -> None:
        profile = self.selected_profile()
        if profile is None:
            self._error("Select a profile before drafting messages.")
            return
        try:
            count = self.context.runner.draft_messages(profile, stage=stage)
        except Exception as exc:
            self._error(str(exc))
            return
        self.refresh_recruiters()
        self.refresh_activity()
        self.show_selected_recruiter_draft()
        self.statusBar().showMessage(f"Created {count} drafts for stage '{stage}'.", 5000)

    def save_template(self) -> None:
        template = MessageTemplate(
            name=self.template_name.text().strip(),
            stage=self.template_stage.currentText(),
            content=self.template_content.toPlainText().strip(),
            active=self.template_active.isChecked(),
        )
        if not template.name or not template.content:
            self._error("Template name and content are required.")
            return
        self.context.database.save_message_template(template)
        self.refresh_activity()
        self.statusBar().showMessage(f"Saved template '{template.name}'.", 5000)

    def save_resume_variant(self) -> None:
        variant = ResumeVariant(
            name=self.resume_name.text().strip(),
            file_path=self.resume_path.text().strip(),
            keywords=_csv(self.resume_keywords.text()),
        )
        if not variant.name or not variant.file_path:
            self._error("Resume name and file path are required.")
            return
        self.context.database.save_resume_variant(variant)
        self.statusBar().showMessage(f"Saved resume variant '{variant.name}'.", 5000)

    def save_screening_answer(self) -> None:
        answer = ScreeningAnswer(
            question_pattern=self.answer_pattern.text().strip(),
            answer_type=self.answer_type.currentText(),
            answer_value=self.answer_value.text().strip(),
        )
        if not answer.question_pattern or not answer.answer_value:
            self._error("Question pattern and answer value are required.")
            return
        self.context.database.save_screening_answer(answer)
        self.statusBar().showMessage("Saved screening answer.", 5000)

    def show_selected_recruiter_draft(self) -> None:
        selected_ranges = self.recruiter_table.selectedRanges()
        if not selected_ranges:
            self.draft_preview.clear()
            return
        row = selected_ranges[0].topRow()
        recruiter_id_item = self.recruiter_table.item(row, 0)
        if recruiter_id_item is None:
            self.draft_preview.clear()
            return
        drafts = self.context.database.list_message_drafts(int(recruiter_id_item.text()))
        if not drafts:
            self.draft_preview.setPlainText("No drafts yet for this recruiter.")
            return
        self.draft_preview.setPlainText(drafts[0].content)

    def _populate_job_table(self, table: QTableWidget, jobs: Iterable) -> None:
        jobs_list = list(jobs)
        table.setRowCount(len(jobs_list))
        for row, job in enumerate(jobs_list):
            apply_path = "Easy Apply" if job.easy_apply_available else (job.external_apply_url or "Manual")
            values = [
                str(job.id or ""),
                job.title,
                job.company,
                job.location,
                job.status.value,
                f"{job.fit_score:.0f}",
                apply_path,
            ]
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.resizeColumnsToContents()

    def _on_profile_selected(self, current: QListWidgetItem | None, _: QListWidgetItem | None) -> None:
        if current is None:
            return
        profile_id = current.data(Qt.ItemDataRole.UserRole)
        profile = self.context.database.get_search_profile(profile_id)
        if profile is None:
            return
        self.profile_name.setText(profile.name)
        self.profile_titles.setPlainText("\n".join(profile.titles))
        self.profile_keywords_include.setText(", ".join(profile.keywords_include))
        self.profile_keywords_exclude.setText(", ".join(profile.keywords_exclude))
        self.profile_locations.setText(", ".join(profile.locations))
        self.profile_work_modes.setText(", ".join(profile.work_modes))
        self.profile_seniority.setText(", ".join(profile.seniority_levels))
        self.profile_blacklist.setPlainText("\n".join(profile.company_blacklist))
        index = self.profile_application_mode.findText(profile.application_mode.value)
        self.profile_application_mode.setCurrentIndex(max(index, 0))

    def _error(self, message: str) -> None:
        QMessageBox.critical(self, "LinkedIn Job Assistant", message)
