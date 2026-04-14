from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from typing import TYPE_CHECKING

from .config import AppPaths
from .database import Database

if TYPE_CHECKING:
    from .ui.automation_controller import AutomationController


@dataclass(slots=True)
class AppContext:
    paths: AppPaths
    database: Database
    logger: Logger
    automation_controller: "AutomationController"
