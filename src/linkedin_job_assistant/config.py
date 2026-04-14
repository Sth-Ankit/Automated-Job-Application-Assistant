from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


APP_NAME = "LinkedIn Job Assistant"


def _default_data_dir() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "linkedin-job-assistant"
    return Path.home() / ".linkedin-job-assistant"


@dataclass(slots=True)
class AppPaths:
    data_dir: Path = field(default_factory=_default_data_dir)
    database_path: Path = field(init=False)
    logs_dir: Path = field(init=False)
    exports_dir: Path = field(init=False)
    browser_profile_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.database_path = self.data_dir / "assistant.db"
        self.logs_dir = self.data_dir / "logs"
        self.exports_dir = self.data_dir / "exports"
        self.browser_profile_dir = self.data_dir / "browser-profile"

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.browser_profile_dir.mkdir(parents=True, exist_ok=True)
