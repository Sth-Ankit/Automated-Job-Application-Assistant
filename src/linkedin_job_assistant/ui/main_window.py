from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
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
        self._automation_buttons: list[QPushButton] = []
        self.setWindowTitle("LinkedIn Job Assistant")
        self.resize(1440, 900)
        self.setStatusBar(QStatusBar())

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self._on_profile_selected)
        self.resume_list = QListWidget()
        self.resume_list.currentItemChanged.connect(self._on_resume_selected)

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
        self._connect_automation_signals()

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
        self.session_button = QPushButton("Open LinkedIn Session")
        self.session_button.clicked.connect(self.open_linkedin_session)
        self.search_button = QPushButton("Run Search")
        self.search_button.clicked.connect(self.run_search)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_all)
        for button in (save_button, self.session_button, self.search_button, refresh_button):
            button_row.addWidget(button)
        left_layout.addLayout(button_row)
        self._register_automation_buttons(self.session_button, self.search_button)

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
        self.apply_button = QPushButton("Run Apply Cycle")
        self.apply_button.clicked.connect(self.run_apply_cycle)
        self.apply_limit = QSpinBox()
        self.apply_limit.setRange(1, 100)
        self.apply_limit.setValue(5)
        controls.addWidget(refresh_button)
        controls.addWidget(QLabel("Max jobs"))
        controls.addWidget(self.apply_limit)
        controls.addWidget(self.apply_button)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(self.queue_table)
        self._register_automation_buttons(self.apply_button)

        self.tabs.addTab(tab, "Application Queue")

    def _build_recruiter_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        controls = QHBoxLayout()
        refresh_button = QPushButton("Refresh Recruiters")
        refresh_button.clicked.connect(self.refresh_recruiters)
        self.find_button = QPushButton("Find Recruiters")
        self.find_button.clicked.connect(self.discover_recruiters)
        self.draft_initial_button = QPushButton("Draft Initial Messages")
        self.draft_initial_button.clicked.connect(lambda: self.draft_messages("initial"))
        self.draft_follow_up_button = QPushButton("Draft Follow Up 1")
        self.draft_follow_up_button.clicked.connect(lambda: self.draft_messages("follow_up_1"))
        controls.addWidget(refresh_button)
        controls.addWidget(self.find_button)
        controls.addWidget(self.draft_initial_button)
        controls.addWidget(self.draft_follow_up_button)
        controls.addStretch()
        layout.addLayout(controls)
        self._register_automation_buttons(
            self.find_button,
            self.draft_initial_button,
            self.draft_follow_up_button,
        )

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
        resume_path_row = QHBoxLayout()
        resume_path_row.addWidget(self.resume_path)
        self.resume_browse_button = QPushButton("Upload Resume")
        self.resume_browse_button.clicked.connect(self.browse_resume_file)
        resume_path_row.addWidget(self.resume_browse_button)
        resume_save = QPushButton("Save Resume Variant")
        resume_save.clicked.connect(self.save_resume_variant)
        resume_form.addRow(QLabel("Saved resumes"))
        resume_form.addRow(self.resume_list)
        resume_form.addRow("Name", self.resume_name)
        resume_form.addRow("Resume file", resume_path_row)
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
        self.refresh_resume_variants()
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

    def refresh_resume_variants(self) -> None:
        current_name = self.resume_name.text().strip()
        self.resume_list.clear()
        for variant in self.context.database.list_resume_variants():
            item = QListWidgetItem(variant.name)
            item.setData(Qt.ItemDataRole.UserRole, variant.id)
            item.setToolTip(variant.file_path)
            self.resume_list.addItem(item)
            if variant.name == current_name:
                self.resume_list.setCurrentItem(item)

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
        self.statusBar().showMessage("Opening LinkedIn browser session...", 5000)
        self.context.automation_controller.open_session()

    def run_search(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            self._error("Select or save a search profile first.")
            return
        self.statusBar().showMessage(f"Searching LinkedIn for '{profile.name}'...", 5000)
        self.context.automation_controller.run_search(profile)

    def run_apply_cycle(self) -> None:
        self.statusBar().showMessage("Running application cycle...", 5000)
        self.context.automation_controller.run_apply_cycle(self.apply_limit.value(), self.selected_profile())

    def discover_recruiters(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            self._error("Select a profile before discovering recruiters.")
            return
        self.statusBar().showMessage("Searching LinkedIn for recruiters...", 5000)
        self.context.automation_controller.discover_recruiters(profile)

    def draft_messages(self, stage: str) -> None:
        profile = self.selected_profile()
        if profile is None:
            self._error("Select a profile before drafting messages.")
            return
        self.statusBar().showMessage(f"Drafting {stage} messages...", 5000)
        self.context.automation_controller.draft_messages(profile, stage)

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
        self.refresh_resume_variants()
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

    def _on_resume_selected(self, current: QListWidgetItem | None, _: QListWidgetItem | None) -> None:
        if current is None:
            return
        for variant in self.context.database.list_resume_variants():
            if variant.id == current.data(Qt.ItemDataRole.UserRole):
                self.resume_name.setText(variant.name)
                self.resume_path.setText(variant.file_path)
                self.resume_keywords.setText(", ".join(variant.keywords))
                return

    def browse_resume_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Resume File",
            "",
            "Resume Files (*.pdf *.doc *.docx);;All Files (*.*)",
        )
        if not file_path:
            return
        self.resume_path.setText(file_path)
        if not self.resume_name.text().strip():
            resume_name = file_path.replace("\\", "/").split("/")[-1].rsplit(".", 1)[0]
            self.resume_name.setText(resume_name)

    def _error(self, message: str) -> None:
        QMessageBox.critical(self, "LinkedIn Job Assistant", message)

    def _register_automation_buttons(self, *buttons: QPushButton) -> None:
        self._automation_buttons.extend(buttons)

    def _set_automation_busy(self, busy: bool) -> None:
        for button in self._automation_buttons:
            button.setEnabled(not busy)
        if busy:
            self.statusBar().showMessage("LinkedIn automation is running...", 0)
        else:
            self.statusBar().clearMessage()

    def _connect_automation_signals(self) -> None:
        controller = self.context.automation_controller
        controller.busy_changed.connect(self._set_automation_busy)
        controller.operation_failed.connect(self._on_operation_failed)
        controller.session_opened.connect(self._on_session_opened)
        controller.search_completed.connect(self._on_search_completed)
        controller.apply_completed.connect(self._on_apply_completed)
        controller.recruiters_discovered.connect(self._on_recruiters_discovered)
        controller.drafts_created.connect(self._on_drafts_created)
        controller.resume_choice_requested.connect(self._on_resume_choice_requested)
        controller.screening_answer_requested.connect(self._on_screening_answer_requested)

    def _on_operation_failed(self, message: str) -> None:
        self.refresh_activity()
        self._error(message)

    def _on_session_opened(self) -> None:
        self.refresh_activity()
        QMessageBox.information(
            self,
            "LinkedIn Session Ready",
            "A LinkedIn browser window has been opened in the background worker. Log in there manually and keep it open while you run search, recruiter, or apply actions.",
        )
        self.statusBar().showMessage("LinkedIn session opened. Complete login in the browser window.", 7000)

    def _on_search_completed(self, count: int) -> None:
        self.refresh_jobs()
        self.refresh_activity()
        self.statusBar().showMessage(f"Search captured {count} jobs.", 5000)

    def _on_apply_completed(self, count: int, _statuses: list[str]) -> None:
        self.refresh_jobs()
        self.refresh_activity()
        self.statusBar().showMessage(f"Processed {count} application attempts.", 5000)

    def _on_recruiters_discovered(self, count: int) -> None:
        self.refresh_recruiters()
        self.refresh_activity()
        self.statusBar().showMessage(f"Discovered {count} recruiters.", 5000)

    def _on_drafts_created(self, count: int, stage: str) -> None:
        self.refresh_recruiters()
        self.refresh_activity()
        self.show_selected_recruiter_draft()
        self.statusBar().showMessage(f"Created {count} drafts for stage '{stage}'.", 5000)

    def _on_resume_choice_requested(self, job_title: str, choices: list[dict[str, str]]) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Choose Resume")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Select the resume to use for '{job_title}':"))
        combo = QComboBox(dialog)
        for choice in choices:
            label = choice["name"]
            if choice.get("keywords"):
                label += f" ({choice['keywords']})"
            combo.addItem(label, choice["name"])
        layout.addWidget(combo)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.context.automation_controller.provide_prompt_response(str(combo.currentData()))
        else:
            self.context.automation_controller.provide_prompt_response(None)

    def _on_screening_answer_requested(self, label: str, answer_type: str, options: list[str]) -> None:
        prompt = (
            f"LinkedIn asked a new {answer_type} question.\n\n"
            f"Question: {label}\n\n"
            "Your answer will be saved and reused next time."
        )
        if options:
            answer, accepted = QInputDialog.getItem(
                self,
                "New Screening Question",
                prompt,
                options,
                0,
                False,
            )
        else:
            answer, accepted = QInputDialog.getText(
                self,
                "New Screening Question",
                prompt,
            )
        self.context.automation_controller.provide_prompt_response(answer if accepted else None)
