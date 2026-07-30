"""Auth-mode behaviour, driven against the local fake Esse3."""

from __future__ import annotations

import pytest

from gradplan.archive import RawArchive
from gradplan.sources.browser import AUTH_AUTO, AUTH_STORAGE, LoginError, Session
from tests.test_browser_integration import (  # noqa: F401 - fixtures reused
    GOOD_PASSWORD,
    GOOD_USER,
    fake_esse3,
)

LIBRETTO = "/auth/studente/Libretto/LibrettoHome.do"


@pytest.fixture
def archive(tmp_path):
    return RawArchive(tmp_path / "raw")


def _session(monkeypatch, tmp_path, archive, mode):
    from gradplan import config

    monkeypatch.setattr(config, "STORAGE_STATE", tmp_path / "storage_state.json")
    try:
        return Session(archive, auth_mode=mode, headless=True, delay=0).start()
    except Exception as exc:  # pragma: no cover - depends on the machine
        pytest.skip(f"Chromium unavailable: {exc}")


def test_auto_uses_env_credentials_when_present(
    fake_esse3, archive, monkeypatch, tmp_path  # noqa: F811
):
    monkeypatch.setenv("UNIPV_USERNAME", GOOD_USER)
    monkeypatch.setenv("UNIPV_PASSWORD", GOOD_PASSWORD)
    handle = _session(monkeypatch, tmp_path, archive, AUTH_AUTO)
    try:
        handle.login(f"{fake_esse3}{LIBRETTO}", success_marker="libretto")
        assert "Libretto" in handle.page.url
    finally:
        handle.close()


def test_auto_reuses_a_saved_session_without_credentials(
    fake_esse3, archive, monkeypatch, tmp_path  # noqa: F811
):
    from gradplan import config

    # First run signs in and leaves a storage state behind ...
    monkeypatch.setenv("UNIPV_USERNAME", GOOD_USER)
    monkeypatch.setenv("UNIPV_PASSWORD", GOOD_PASSWORD)
    first = _session(monkeypatch, tmp_path, archive, AUTH_AUTO)
    try:
        first.login(f"{fake_esse3}{LIBRETTO}", success_marker="libretto")
    finally:
        first.close()
    assert config.STORAGE_STATE.exists()

    # ... so a second run needs no credentials at all.
    monkeypatch.delenv("UNIPV_USERNAME", raising=False)
    monkeypatch.delenv("UNIPV_PASSWORD", raising=False)
    second = _session(monkeypatch, tmp_path, archive, AUTH_STORAGE)
    try:
        second.login(f"{fake_esse3}{LIBRETTO}", success_marker="libretto")
        assert "Libretto" in second.page.url
    finally:
        second.close()
