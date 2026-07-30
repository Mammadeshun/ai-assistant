"""End-to-end test of the Playwright scraping path against a local fake Esse3.

This exercises the parts that cannot be checked by parsing fixtures: browser
launch, form-based login, redirect handling, session reuse, and the archiving
of every page actually visited.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from gradplan.archive import RawArchive
from gradplan.models import PASSED
from gradplan.parsers import esse3 as esse3_parser
from gradplan.sources.browser import AUTH_ENV, AUTH_STORAGE, LoginError, Session

FIXTURES = Path(__file__).parent / "fixtures"

LOGIN_PAGE = """<html><body><h1>Login</h1>
<form method="POST" action="/auth/Logon.do">
  <input type="text" id="username" name="username"/>
  <input type="password" id="password" name="password"/>
  <button type="submit" name="_eventId_proceed">Accedi</button>
</form></body></html>"""

GOOD_USER, GOOD_PASSWORD = "TESTUSER", "s3cret"


class FakeEsse3(BaseHTTPRequestHandler):
    """Minimal stand-in: cookie-gated libretto behind a login form."""

    def log_message(self, *args):  # silence the test output
        pass

    def _send(self, status: int, body: str = "", headers: dict[str, str] | None = None):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    @property
    def _authenticated(self) -> bool:
        return "session=ok" in self.headers.get("Cookie", "")

    def do_GET(self):
        if self.path.startswith("/auth/studente/Libretto"):
            if not self._authenticated:
                self._send(302, "", {"Location": "/auth/Logon.do"})
                return
            self._send(200, (FIXTURES / "esse3_libretto.html").read_text(encoding="utf-8"))
            return
        if self.path.startswith("/auth/studente/Carriera"):
            if not self._authenticated:
                self._send(302, "", {"Location": "/auth/Logon.do"})
                return
            self._send(200, "<html><body><table><tr><td>Matricola:</td><td>123456</td></tr></table></body></html>")
            return
        self._send(200, LOGIN_PAGE)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        if f"username={GOOD_USER}" in body and f"password={GOOD_PASSWORD}" in body:
            self._send(
                302,
                "",
                {"Location": "/auth/studente/Libretto/LibrettoHome.do", "Set-Cookie": "session=ok; Path=/"},
            )
        else:
            self._send(200, LOGIN_PAGE + "<p>Credenziali errate</p>")


@pytest.fixture(scope="module")
def fake_esse3():
    server = HTTPServer(("127.0.0.1", 0), FakeEsse3)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def archive(tmp_path):
    return RawArchive(tmp_path / "raw")


def _session(archive, monkeypatch, tmp_path, mode=AUTH_ENV):
    """A Session whose storage state is isolated to the test's tmp dir."""
    from gradplan import config

    monkeypatch.setattr(config, "STORAGE_STATE", tmp_path / "storage_state.json")
    try:
        return Session(archive, auth_mode=mode, headless=True, delay=0).start()
    except Exception as exc:  # pragma: no cover - depends on the machine
        pytest.skip(f"Chromium unavailable: {exc}")


def test_login_then_scrape_and_archive(fake_esse3, archive, monkeypatch, tmp_path):
    monkeypatch.setenv("UNIPV_USERNAME", GOOD_USER)
    monkeypatch.setenv("UNIPV_PASSWORD", GOOD_PASSWORD)
    handle = _session(archive, monkeypatch, tmp_path)
    try:
        handle.login(f"{fake_esse3}/auth/studente/Libretto/LibrettoHome.do", success_marker="libretto")
        handle.goto(
            f"{fake_esse3}/auth/studente/Libretto/LibrettoHome.do",
            source="esse3",
            label="libretto",
        )
    finally:
        handle.close()

    # The visited page must be recoverable from the archive alone ...
    record = archive.latest("esse3", "libretto")
    assert record is not None and record.path.exists()

    # ... and parse into the career it represents.
    exams, diagnostics = esse3_parser.parse_libretto(record.read_text())
    assert diagnostics == []
    by_name = {e.name: e for e in exams}
    assert by_name["Calculus"].status == PASSED
    assert by_name["Calculus"].mark == 30 and by_name["Calculus"].lode


def test_bad_credentials_raise_and_archive_the_failing_page(
    fake_esse3, archive, monkeypatch, tmp_path
):
    monkeypatch.setenv("UNIPV_USERNAME", GOOD_USER)
    monkeypatch.setenv("UNIPV_PASSWORD", "wrong")
    handle = _session(archive, monkeypatch, tmp_path)
    try:
        with pytest.raises(LoginError):
            handle.login(
                f"{fake_esse3}/auth/studente/Libretto/LibrettoHome.do",
                success_marker="libretto",
            )
    finally:
        handle.close()
    assert archive.latest("debug", "login-failed") is not None


def test_storage_mode_refuses_to_guess_credentials(
    fake_esse3, archive, monkeypatch, tmp_path
):
    """With no saved session, 'storage' mode must fail loudly, not try a login."""
    monkeypatch.delenv("UNIPV_USERNAME", raising=False)
    monkeypatch.delenv("UNIPV_PASSWORD", raising=False)
    handle = _session(archive, monkeypatch, tmp_path, mode=AUTH_STORAGE)
    try:
        with pytest.raises(LoginError, match="--auth interactive"):
            handle.login(
                f"{fake_esse3}/auth/studente/Libretto/LibrettoHome.do",
                success_marker="libretto",
            )
    finally:
        handle.close()
