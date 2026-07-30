"""Static configuration: endpoints, paths, and degree-course constants.

Credentials are never stored here. They are read from the environment
(see `Credentials.from_env`) so that nothing secret ends up in git.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
REFERENCE_DIR = REPO_ROOT / "reference"

CAREER_JSON = DATA_DIR / "career.json"
PLAN_JSON = DATA_DIR / "graduation_plan.json"

# --- Degree course -----------------------------------------------------------
# Interateneo BSc in Artificial Intelligence (class L-31), administrative seat
# Pavia, jointly with Milano Statale and Milano-Bicocca.
DEGREE_CODE = "08424"
DEGREE_NAME = "Artificial Intelligence (L-31), interateneo Pavia / Statale / Bicocca"
TOTAL_CFU_REQUIRED = 180
FINAL_EXAM_CODE = "509535"
FINAL_EXAM_CFU = 3

UNIVERSITIES = {
    "pavia": "Università di Pavia",
    "statale": "Università degli Studi di Milano (Statale)",
    "bicocca": "Università di Milano-Bicocca",
}

# --- Public sources (no authentication) --------------------------------------
BAI_BASE = "https://bai.unipv.it"
BAI_ENROLLED_STUDENTS = f"{BAI_BASE}/home-eng/enrolled-students/"
BAI_STUDY_PLAN = f"{BAI_BASE}/home-eng/study-plan/"

# Published Google Sheet holding per-course exam sitting dates, one tab per
# session. Tab ids are discovered from the enrolled-students page at runtime;
# these are the values seen at the time of writing and act as a fallback.
BAI_EXAM_SHEET = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ9uW092t6FAybzWLr-"
    "jqiH8I8EJ5-SfLsYcu6Vo6CJpUyu0mc9gvWIxdhLIkPHn5mg0_cKrLjO-dKY/pub"
)
BAI_EXAM_SHEET_TABS = {
    "winter": "1337270851",
    "summer": "506643480",
    "autumn": "4277881",
}

# --- Authenticated sources ---------------------------------------------------
ESSE3_BASE = "https://studentionline.unipv.it"
ESSE3_LOGIN = f"{ESSE3_BASE}/auth/Logon.do"
ESSE3_LIBRETTO = f"{ESSE3_BASE}/auth/studente/Libretto/LibrettoHome.do"
ESSE3_CAREER = f"{ESSE3_BASE}/auth/studente/Carriera/CarrieraHome.do"
ESSE3_STUDY_PLAN = f"{ESSE3_BASE}/auth/studente/Piani/PianoHome.do"
ESSE3_EXAM_ENROLLMENTS = f"{ESSE3_BASE}/auth/studente/Appelli/BachecaPrenotazioni.do"
ESSE3_AVAILABLE_EXAMS = f"{ESSE3_BASE}/auth/studente/Appelli/AppelliF.do"

KIRO_BASE = "https://elearning.unipv.it"
# Moodle SAML2 entry point; idp id is UniPV's in the elearning SP config.
KIRO_SAML_LOGIN = (
    f"{KIRO_BASE}/auth/saml2/login.php"
    "?wants&idp=28c4b89f3ffa1f445c94d30f5ee49037&passive=off"
)
KIRO_COURSES_API = f"{KIRO_BASE}/lib/ajax/service.php"

# --- Politeness --------------------------------------------------------------
REQUEST_DELAY_SECONDS = 2.0
NAV_TIMEOUT_MS = 45_000
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Browser storage state, so a successful interactive login can be reused
# without re-entering credentials on every run.
STORAGE_STATE = DATA_DIR / "storage_state.json"

# Explicit Chromium binary. Needed where the installed Playwright package pins a
# browser build that is not the one present on the machine; set
# GRADPLAN_CHROMIUM to override, otherwise a known location is tried as a
# fallback before giving up.
CHROMIUM_PATH = os.environ.get("GRADPLAN_CHROMIUM")
CHROMIUM_FALLBACKS = (
    "/opt/pw-browsers/chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
)


def browser_proxy() -> dict[str, str] | None:
    """Proxy for the browser, taken from the usual environment variables.

    Chromium does not read HTTPS_PROXY on its own, so it has to be passed
    explicitly. Returns None on a normal machine with direct connectivity.
    """
    server = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
    )
    if not server:
        return None
    proxy: dict[str, str] = {"server": server}
    no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    if no_proxy:
        proxy["bypass"] = no_proxy
    return proxy


def chromium_executable() -> str | None:
    """First Chromium that actually exists, or None to use Playwright's own."""
    from pathlib import Path as _Path

    candidates = [CHROMIUM_PATH, *CHROMIUM_FALLBACKS] if CHROMIUM_PATH else CHROMIUM_FALLBACKS
    for candidate in candidates:
        if candidate and _Path(candidate).exists():
            return candidate
    return None


@dataclass(frozen=True)
class Credentials:
    """UniPV single sign-on credentials, read from the environment."""

    username: str
    password: str

    @classmethod
    def from_env(cls) -> "Credentials | None":
        user = os.environ.get("UNIPV_USERNAME")
        pwd = os.environ.get("UNIPV_PASSWORD")
        if not user or not pwd:
            return None
        return cls(username=user, password=pwd)


def ensure_dirs() -> None:
    for d in (DATA_DIR, RAW_DIR, REFERENCE_DIR):
        d.mkdir(parents=True, exist_ok=True)
