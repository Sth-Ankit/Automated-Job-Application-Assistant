from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus


class LinkedInClient:
    JOB_CARD_SELECTOR = "li.jobs-search-results__list-item, li.scaffold-layout__list-item, div.job-card-container"
    PEOPLE_CARD_SELECTOR = "li.reusable-search__result-container, div.entity-result"

    def __init__(self) -> None:
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None
        self._page: Any | None = None
        self._timeout_error: type[Exception] = RuntimeError

    def _require_playwright(self) -> tuple[Any, type[Exception]]:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run 'pip install -e .[dev]' and 'playwright install chromium'."
            ) from exc
        return sync_playwright, PlaywrightTimeoutError

    def start(self, headless: bool = False) -> None:
        if self._page is not None:
            return
        sync_playwright, timeout_error = self._require_playwright()
        self._timeout_error = timeout_error
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=headless)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()

    def stop(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    @property
    def page(self) -> Any:
        if self._page is None:
            raise RuntimeError("LinkedIn browser session has not been started.")
        return self._page

    def open_login(self) -> None:
        self.start(headless=False)
        self.page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

    def is_authenticated(self) -> bool:
        if self._page is None:
            return False
        self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        self.page.wait_for_timeout(1000)
        return "feed" in self.page.url or "mynetwork" in self.page.url

    def ensure_authenticated(self) -> None:
        if not self.is_authenticated():
            raise RuntimeError("LinkedIn session is not authenticated. Open a session and log in manually first.")

    def open_job(self, url: str) -> Any:
        self.ensure_authenticated()
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1200)
        return self.page

    def fetch_job_cards(self, search_url: str, *, limit: int = 20) -> list[dict[str, Any]]:
        self.ensure_authenticated()
        page = self.page
        page.goto(search_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        cards = page.locator(self.JOB_CARD_SELECTOR)
        count = min(cards.count(), limit)
        jobs: list[dict[str, Any]] = []
        for index in range(count):
            card = cards.nth(index)
            try:
                card.scroll_into_view_if_needed()
                card.click(timeout=1500)
                page.wait_for_timeout(800)
                job_url = self._extract_job_url(card, page)
                linkedin_job_id = self._extract_job_id(card, job_url, index)
                job = {
                    "linkedin_job_id": linkedin_job_id,
                    "title": self._extract_text(card, ["strong", ".job-card-list__title", ".artdeco-entity-lockup__title"]) or "Unknown Title",
                    "company": self._extract_text(card, [".artdeco-entity-lockup__subtitle", ".job-card-container__company-name", ".subtitle"]) or "Unknown Company",
                    "location": self._extract_text(card, [".job-card-container__metadata-item", ".job-search-card__location", ".job-card-container__metadata-wrapper"]) or "",
                    "job_url": job_url,
                    "easy_apply_available": self._locator_exists(page, "button:has-text('Easy Apply')"),
                    "external_apply_url": self._extract_external_apply_url(page),
                    "raw_metadata": {
                        "snippet": self._extract_text(page, [".jobs-description-content__text", ".jobs-box__html-content", ".jobs-description__content"]),
                        "source_search_url": search_url,
                    },
                }
                jobs.append(job)
            except Exception:
                continue
        return jobs

    def find_recruiters(self, company: str, role: str, *, limit: int = 10) -> list[dict[str, Any]]:
        self.ensure_authenticated()
        query = quote_plus(f"{company} recruiter {role}")
        url = f"https://www.linkedin.com/search/results/people/?keywords={query}"
        page = self.page
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        cards = page.locator(self.PEOPLE_CARD_SELECTOR)
        count = min(cards.count(), limit)
        recruiters: list[dict[str, Any]] = []
        for index in range(count):
            card = cards.nth(index)
            try:
                profile_url = self._extract_profile_url(card)
                if not profile_url:
                    continue
                recruiters.append(
                    {
                        "name": self._extract_text(card, ["span[aria-hidden='true']", ".entity-result__title-text"]) or f"Recruiter {index + 1}",
                        "title": self._extract_text(card, [".entity-result__primary-subtitle", ".entity-result__summary"]) or "Recruiter",
                        "company": company,
                        "linkedin_profile_url": profile_url,
                    }
                )
            except Exception:
                continue
        return recruiters

    @staticmethod
    def _locator_exists(page: Any, selector: str) -> bool:
        try:
            return page.locator(selector).count() > 0
        except Exception:
            return False

    @staticmethod
    def _extract_text(scope: Any, selectors: list[str]) -> str:
        for selector in selectors:
            try:
                locator = scope.locator(selector).first
                if locator.count() == 0:
                    continue
                text = locator.text_content() or ""
                cleaned = " ".join(text.split())
                if cleaned:
                    return cleaned
            except Exception:
                continue
        return ""

    @staticmethod
    def _extract_job_url(card: Any, page: Any) -> str:
        for selector in ("a[href*='/jobs/view/']", "a.job-card-list__title", "a"):
            try:
                locator = card.locator(selector).first
                href = locator.get_attribute("href")
                if href:
                    if href.startswith("http"):
                        return href
                    return f"https://www.linkedin.com{href}"
            except Exception:
                continue
        return page.url

    @staticmethod
    def _extract_job_id(card: Any, job_url: str, index: int) -> str:
        for attribute in ("data-job-id", "data-occludable-job-id"):
            try:
                value = card.get_attribute(attribute)
                if value:
                    return value
            except Exception:
                continue
        match = re.search(r"/jobs/view/(\d+)", job_url)
        if match:
            return match.group(1)
        return f"card-{index}-{abs(hash(job_url))}"

    @staticmethod
    def _extract_external_apply_url(page: Any) -> str | None:
        try:
            locators = [
                "a[href*='workday']",
                "a[href*='greenhouse']",
                "a[href*='lever.co']",
                "a[href^='http']",
            ]
            for selector in locators:
                locator = page.locator(selector).first
                if locator.count() == 0:
                    continue
                href = locator.get_attribute("href")
                if href and "linkedin.com" not in href:
                    return href
        except Exception:
            return None
        return None

    @staticmethod
    def _extract_profile_url(card: Any) -> str | None:
        for selector in ("a[href*='/in/']", "a.app-aware-link", "a"):
            try:
                locator = card.locator(selector).first
                href = locator.get_attribute("href")
                if href and "/in/" in href:
                    if href.startswith("http"):
                        return href
                    return f"https://www.linkedin.com{href}"
            except Exception:
                continue
        return None
