"""Look at a business's web presence and write down what is broken.

Every finding has to be something you could show the owner in one screenshot,
because that is what the opener refers to. Vague complaints ("your SEO could
be better") are not findings.

Network checks run for every lead. The mobile check starts headless Chrome,
which is the memory hog on a 4 GB box, so it reuses one browser for the whole
run and can be switched off with SCAN_MOBILE=0.
"""

import os
import ssl
import time
import socket
import datetime
import urllib.parse

import requests

SCAN_TIMEOUT = int(os.environ.get("SCAN_TIMEOUT", "12"))
SLOW_SECONDS = float(os.environ.get("SCAN_SLOW_SECONDS", "4"))
CERT_WARN_DAYS = int(os.environ.get("SCAN_CERT_WARN_DAYS", "21"))
SHOTS_DIR = os.environ.get("SCAN_SHOTS_DIR", "data/shots")

# What each finding is worth when deciding who to contact first.
SEVERITY = {
    "no_website": 5,
    "site_down": 5,
    "ssl_expired": 5,
    "not_mobile": 4,
    "ssl_expiring": 3,
    "slow": 2,
    "no_english": 1,
}

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _finding(code, detail):
    return {"code": code, "severity": SEVERITY.get(code, 1), "detail": detail}


def _normalise(url):
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def check_certificate(hostname, port=443):
    """Returns a finding when the certificate is expired or nearly so."""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port), timeout=SCAN_TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as tls:
                cert = tls.getpeercert()
    except ssl.SSLCertVerificationError as e:
        # Expired, self-signed or wrong-host: the browser shows a full-page
        # warning, which is about as concrete as evidence gets.
        return _finding("ssl_expired", str(e.verify_message or e)[:120])
    except (socket.timeout, socket.gaierror, ConnectionError, OSError) as e:
        return None  # reachability is the HTTP check's job, not this one

    not_after = cert.get("notAfter")
    if not not_after:
        return None
    expires = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
    days_left = (expires - datetime.datetime.utcnow()).days
    if days_left < 0:
        return _finding("ssl_expired", f"expired {abs(days_left)} days ago")
    if days_left <= CERT_WARN_DAYS:
        return _finding("ssl_expiring", f"expires in {days_left} days")
    return None


def _dedupe(findings):
    """One finding per code: the TLS probe and the HTTP request both notice a
    bad certificate, and saying it twice in an opener looks automated."""
    seen, out = set(), []
    for f in findings:
        if f["code"] not in seen:
            seen.add(f["code"])
            out.append(f)
    return out


def check_site(url):
    """Reachability, speed, certificate and language. No browser needed."""
    findings = []
    url = _normalise(url)
    if not url:
        return [_finding("no_website", "no website on record")]

    host = urllib.parse.urlparse(url).hostname
    if host:
        cert_finding = check_certificate(host)
        if cert_finding:
            findings.append(cert_finding)

    started = time.time()
    try:
        response = requests.get(url, timeout=SCAN_TIMEOUT, allow_redirects=True,
                                headers={"User-Agent": USER_AGENT})
        elapsed = time.time() - started
    except requests.exceptions.SSLError as e:
        findings.append(_finding("ssl_expired", str(e)[:120]))
        return _dedupe(findings)
    except requests.RequestException as e:
        findings.append(_finding("site_down", type(e).__name__))
        return _dedupe(findings)

    if response.status_code >= 500:
        findings.append(_finding("site_down", f"HTTP {response.status_code}"))
        return _dedupe(findings)
    if elapsed > SLOW_SECONDS:
        findings.append(_finding("slow", f"{elapsed:.1f}s to first byte"))

    html = response.text[:200000].lower()
    if 'hreflang="en' not in html and "/en/" not in html and "lang=\"en" not in html:
        findings.append(_finding("no_english", "no English version found"))
    return _dedupe(findings)


def check_mobile(driver, url, shot_path=None):
    """Render at phone width and look for a page that does not fit.

    Two symptoms, both visible in a screenshot: no viewport meta tag at all,
    and content wider than the screen so the reader has to pan sideways.
    """
    url = _normalise(url)
    driver.set_window_size(390, 844)   # iPhone-ish
    driver.get(url)
    time.sleep(2)

    has_viewport = driver.execute_script(
        "return !!document.querySelector('meta[name=\"viewport\"]')")
    doc_width = driver.execute_script("return document.documentElement.scrollWidth")
    win_width = driver.execute_script("return window.innerWidth")
    overflow = doc_width - win_width

    if shot_path:
        os.makedirs(os.path.dirname(shot_path), exist_ok=True)
        driver.save_screenshot(shot_path)

    if not has_viewport:
        return _finding("not_mobile", "no viewport meta tag; desktop layout on phones")
    if overflow > 20:
        return _finding("not_mobile", f"content {overflow}px wider than the screen")
    return None


def browser():
    """One headless Chrome for a whole run. Caller closes it."""
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options

    options = Options()
    for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                "--disable-gpu", "--window-size=390,844"):
        options.add_argument(arg)
    options.add_argument(f"user-agent={USER_AGENT}")
    if os.environ.get("CHROME_BINARY"):
        options.binary_location = os.environ["CHROME_BINARY"]

    driver_path = os.environ.get("CHROMEDRIVER_PATH", "")
    if driver_path and os.path.exists(driver_path):
        service = Service(driver_path)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def scan_lead(lead, driver=None):
    """All checks for one lead. Returns (findings, screenshot path or None)."""
    findings = check_site(lead.get("website"))
    shot = None
    codes = {f["code"] for f in findings}

    if driver and lead.get("website") and not codes & {"no_website", "site_down", "ssl_expired"}:
        shot = os.path.join(SHOTS_DIR, f"lead-{lead['id']}.png")
        try:
            mobile = check_mobile(driver, lead["website"], shot)
            if mobile:
                findings.append(mobile)
            else:
                shot = None  # nothing to show
        except Exception as e:
            print(f"   mobile check failed for {lead['name']}: {type(e).__name__}")
            shot = None

    findings.sort(key=lambda f: -f["severity"])
    return findings, shot


def score(findings):
    """Highest severity wins; ties broken by how much is wrong."""
    if not findings:
        return 0
    return max(f["severity"] for f in findings) * 10 + len(findings)
