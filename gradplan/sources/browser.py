"""Playwright session shared by the authenticated scrapers.

Three authentication modes are supported, because UniPV single sign-on may or
may not present a second factor:

``interactive``
    Opens a headed browser, lets you sign in by hand (including any 2FA), then
    saves the browser storage state. Nothing secret is read or written by the
    tool itself.
``storage``
    Reuses a previously saved storage state. No credentials involved.
``env``
    Fills the SSO form from ``UNIPV_USERNAME`` / ``UNIPV_PASSWORD``.

Navigation is strictly sequential with a delay between requests, and every
response body is archived before it is parsed.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from .. import config
from ..archive import ArchivedResponse, RawArchive

AUTH_AUTO = "auto"
AUTH_INTERACTIVE = "interactive"
AUTH_STORAGE = "storage"
AUTH_ENV = "env"

# Fields on the UniPV / IDEM Shibboleth login form.
USERNAME_SELECTORS = (
    "input#username",
    "input[name='username']",
    "input[name='j_username']",
    "input[type='text']:visible",
)
PASSWORD_SELECTORS = (
    "input#password",
    "input[name='password']",
    "input[name='j_password']",
    "input[type='password']:visible",
)
SUBMIT_SELECTORS = (
    "button[name='_eventId_proceed']",
    "input[name='_eventId_proceed']",
    "button[type='submit']",
    "input[type='submit']",
)


class LoginError(RuntimeError):
    pass


class Session:
    """A logged-in browser context that archives everything it downloads."""

    def __init__(
        self,
        archive: RawArchive,
        *,
        auth_mode: str = AUTH_STORAGE,
        headless: bool = True,
        delay: float | None = None,
    ) -> None:
        self.archive = archive
        self.auth_mode = auth_mode
        self.headless = headless
        self.delay = config.REQUEST_DELAY_SECONDS if delay is None else delay
        self._playwright = None
        self._browser = None
        self.context = None
        self.page = None

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> "Session":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        launch_headless = self.headless and self.auth_mode != AUTH_INTERACTIVE
        launch_kwargs: dict = {"headless": launch_headless}
        proxy = config.browser_proxy()
        if proxy:
            launch_kwargs["proxy"] = proxy
        try:
            self._browser = self._playwright.chromium.launch(**launch_kwargs)
        except Exception:
            # Playwright's pinned browser build may not be the one installed.
            executable = config.chromium_executable()
            if executable is None:
                raise
            self._browser = self._playwright.chromium.launch(
                executable_path=executable, **launch_kwargs
            )

        storage = None
        if self.auth_mode != AUTH_INTERACTIVE and config.STORAGE_STATE.exists():
            storage = str(config.STORAGE_STATE)

        self.context = self._browser.new_context(
            user_agent=config.USER_AGENT,
            storage_state=storage,
            locale="it-IT",
        )
        self.context.set_default_navigation_timeout(config.NAV_TIMEOUT_MS)
        self.page = self.context.new_page()
        return self

    def close(self) -> None:
        if self.context is not None:
            try:
                self.context.storage_state(path=str(config.STORAGE_STATE))
            except Exception:  # noqa: BLE001 - saving state is best effort
                pass
        for closer in (self._browser, self._playwright):
            if closer is None:
                continue
            try:
                closer.close() if hasattr(closer, "close") else closer.stop()
            except Exception:  # noqa: BLE001
                pass

    # -- navigation ---------------------------------------------------------
    def goto(self, url: str, *, source: str, label: str) -> ArchivedResponse:
        """Navigate, archive the resulting HTML, and pause before the next hop."""
        response = self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_load_state("networkidle", timeout=config.NAV_TIMEOUT_MS)
        record = self.archive.save(
            source=source,
            label=label,
            url=self.page.url,
            payload=self.page.content(),
            kind="html",
            status=response.status if response else None,
        )
        time.sleep(self.delay)
        return record

    def post_json(self, url: str, payload, *, source: str, label: str) -> ArchivedResponse:
        """POST a JSON body from inside the authenticated context."""
        response = self.context.request.post(url, data=payload)
        record = self.archive.save(
            source=source,
            label=label,
            url=url,
            payload=response.text(),
            kind="json",
            status=response.status,
        )
        time.sleep(self.delay)
        return record

    def save_current(self, *, source: str, label: str) -> ArchivedResponse:
        return self.archive.save(
            source=source,
            label=label,
            url=self.page.url,
            payload=self.page.content(),
            kind="html",
        )

    # -- authentication -----------------------------------------------------
    def login(self, entry_url: str, *, success_marker: str) -> None:
        """Reach an authenticated state at ``entry_url``.

        ``success_marker`` is a substring expected in the URL or page content
        once the session is authenticated.
        """
        self.page.goto(entry_url, wait_until="domcontentloaded")

        if self._looks_authenticated(success_marker):
            return

        if self.auth_mode == AUTH_INTERACTIVE:
            self._wait_for_human(success_marker)
        elif self.auth_mode == AUTH_ENV:
            self._submit_credentials()
        elif self.auth_mode == AUTH_AUTO:
            # The saved session is gone or expired. Prefer handing the login
            # back to the user over guessing at credentials.
            if config.Credentials.from_env() is not None:
                self._submit_credentials()
            else:
                self._wait_for_human(success_marker)
        else:
            raise LoginError(
                "Not authenticated and no saved session. Run once with "
                "--auth interactive to sign in by hand, or set UNIPV_USERNAME "
                "and UNIPV_PASSWORD and use --auth env."
            )

        if not self._looks_authenticated(success_marker):
            self.archive.save(
                source="debug",
                label="login-failed",
                url=self.page.url,
                payload=self.page.content(),
                kind="html",
            )
            raise LoginError(
                f"Login did not reach an authenticated page (at {self.page.url}). "
                "The failing page was archived under data/raw/debug/."
            )
        self.context.storage_state(path=str(config.STORAGE_STATE))

    def _looks_authenticated(self, success_marker: str) -> bool:
        self.page.wait_for_load_state("networkidle", timeout=config.NAV_TIMEOUT_MS)
        url = self.page.url.lower()
        if "logon" in url or "idp" in url or "login" in url:
            return False
        return success_marker.lower() in url or success_marker.lower() in self.page.content().lower()

    def _submit_credentials(self) -> None:
        credentials = config.Credentials.from_env()
        if credentials is None:
            raise LoginError(
                "--auth env requires UNIPV_USERNAME and UNIPV_PASSWORD in the environment."
            )
        username = self._first_visible(USERNAME_SELECTORS)
        password = self._first_visible(PASSWORD_SELECTORS)
        if username is None or password is None:
            raise LoginError(f"No login form found at {self.page.url}")
        username.fill(credentials.username)
        password.fill(credentials.password)
        submit = self._first_visible(SUBMIT_SELECTORS)
        if submit is None:
            password.press("Enter")
        else:
            submit.click()
        self.page.wait_for_load_state("networkidle", timeout=config.NAV_TIMEOUT_MS)

    def _first_visible(self, selectors: tuple[str, ...]):
        for selector in selectors:
            locator = self.page.locator(selector).first
            try:
                if locator.count() and locator.is_visible():
                    return locator
            except Exception:  # noqa: BLE001 - selector may not apply on this page
                continue
        return None

    def _wait_for_human(self, success_marker: str, timeout_s: int = 300) -> None:
        print(
            "\n  A browser window is open. Sign in to UniPV there "
            "(including any second factor).\n"
            f"  Waiting up to {timeout_s}s for an authenticated page...\n"
        )
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._looks_authenticated(success_marker):
                return
            time.sleep(2)
        raise LoginError("Timed out waiting for interactive login.")


@contextmanager
def session(
    archive: RawArchive,
    *,
    auth_mode: str = AUTH_STORAGE,
    headless: bool = True,
    delay: float | None = None,
) -> Iterator[Session]:
    handle = Session(archive, auth_mode=auth_mode, headless=headless, delay=delay).start()
    try:
        yield handle
    finally:
        handle.close()
