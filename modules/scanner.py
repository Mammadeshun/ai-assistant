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
    # Observed problems outrank inferred ones. no_website comes from a missing
    # OpenStreetMap tag, which is a guess about the practice, not something
    # seen on it - so it ranks below anything a screenshot can prove.
    # Dropped below the send threshold on 2026-09-23. This is not an
    # observation: it means OpenStreetMap has no website tag, and an audit
    # found live sites - showing the very number we were about to message -
    # behind several of them. 8 of the 9 queued WhatsApp messages were built
    # on this guess. It stays visible in the app, but it no longer writes to
    # anyone until something actually searches for the practice.
    "no_website": 1,
    # Same fact, but checked: somebody searched the web for this practice and
    # found no site of their own. Only this one may be written to; the guess
    # above may not. Set by hand today - the server cannot search yet, because
    # every engine blocks it.
    "no_site_found": 3,
    "site_down": 5,
    "ssl_expired": 5,
    "not_mobile": 4,
    # Wider than the screen, but the text fits: a map, a banner, one long
    # line. True, and worth mentioning on a call; not worth a stranger's
    # first message, because the owner opens the page and it reads fine.
    "mobile_overflow": 1,
    # The page a map listing links to is gone, the site is not. Worth a
    # sentence on a call; "your site is down" would be false.
    "listed_page_gone": 1,
    "ssl_expiring": 3,
    # Demoted 2026-09-23: one measurement, from a data centre in Finland. The
    # audit found a site stored as 12.4s that answers in 0.39s from elsewhere.
    # It stays as context for a call; it is not something to assert in writing.
    "slow": 1,
    "no_english": 1,
    # The certificate warning a browser actually shows, told apart. Only the
    # first two are worth a message: a missing intermediate certificate is
    # filled in by every modern browser, and the audit found us calling a
    # valid-until-December certificate "expired" because of one.
    "ssl_wrong_host": 4,
    "ssl_chain": 0,
    # The domain itself is gone - "your site is down right now" is the wrong
    # sentence for that; they have probably moved.
    "domain_gone": 3,
    # Not verdicts: a record that we could not look, so nothing is claimed and
    # the lead is not mistaken for one with a healthy site.
    "blocked": 0,
    "scan_error": 0,
    "social_only": 0,
}

# A judgement is only worth sending if the code is still worth this much.
SENDABLE = 2

# Someone else's site: a Facebook page is not their website, and its
# certificate is Meta's problem. We audited ourselves telling a practice that
# facebook.com's certificate was expiring.
SOCIAL_HOSTS = ("facebook.com", "fb.me", "instagram.com", "linkedin.com", "twitter.com",
                "x.com", "wa.me", "whatsapp.com", "tiktok.com", "youtube.com",
                "paginegialle.it", "paginebianche.it", "miodottore.it", "linktr.ee")

# A site can refuse to show itself to a scanner: Cloudflare and friends answer
# a bot with a block page or a challenge. Whatever comes back then says
# nothing about the real site - the first false claim sent to a prospect came
# from measuring Cloudflare's own block page and calling his site broken.
BLOCKED_STATUS = {401, 403, 405, 406, 429, 503}
CHALLENGE_MARKERS = ("just a moment", "attention required", "cf-browser-verification",
                     "verifying you are human", "checking your browser", "access denied",
                     "enable javascript and cookies", "captcha", "cf-challenge", "ddos-guard")


def _is_challenge(text, title=""):
    blob = f"{title} {text[:4000]}".lower()
    return any(m in blob for m in CHALLENGE_MARKERS)


# Kept current on purpose. With the old Chrome/120 string, 8 sites answered
# the scanner 403 and were filed as "nothing wrong"; the same sites answer 200
# to a current one.
CHROME_VERSION = os.environ.get("SCAN_CHROME_VERSION", "153")
USER_AGENT = (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              f"(KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36")
# What the mobile check must look like, because we say "from a phone".
MOBILE_UA = (f"Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
             f"(KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Mobile Safari/537.36")


def _finding(code, detail):
    return {"code": code, "severity": SEVERITY.get(code, 1), "detail": detail}


def _normalise(url):
    """Clean up what the map data gives us.

    One lead was stored as https://studiodentisticogp.it/https://studiodentisticogp.it/,
    which 404s; we measured that 404 page and queued a claim about it. When an
    address contains a second address, keep the last one.
    """
    if not url:
        return None
    url = url.strip()
    for scheme in ("https://", "http://"):
        cut = url.rfind(scheme)
        if cut > 0:
            url = url[cut:]
            break
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
        # Which warning the browser shows depends on why verification failed,
        # and so does whether it shows one at all.
        reason = str(e.verify_message or e)
        low = reason.lower()
        if "expired" in low:
            return _finding("ssl_expired", reason[:120])
        if "hostname mismatch" in low or "doesn't match" in low or "ip address mismatch" in low:
            return _finding("ssl_wrong_host", reason[:120])
        if "unable to get local issuer" in low or "self-signed" in low or "self signed" in low:
            # Browsers carry the missing intermediate; this is invisible to a
            # visitor, so it is recorded but never sent.
            return _finding("ssl_chain", reason[:120])
        return _finding("ssl_wrong_host", reason[:120])
    except (socket.timeout, socket.gaierror, ConnectionError, OSError) as e:
        return None  # reachability is the HTTP check's job, not this one

    return _expiry_finding(cert)


# These CAs issue short certificates that the host renews by itself, usually
# 30 days before expiry. Sixteen days left on one of them is a renewal that is
# late, not one that has failed, and "your certificate is about to expire"
# sent today can be false by the time it is read. Seven days left is a
# renewal that has stopped.
AUTO_RENEWING_CAS = ("let's encrypt", "zerossl", "google trust services", "buypass")
AUTO_RENEW_WARN_DAYS = 7


def _issuer_org(cert):
    for rdn in cert.get("issuer", ()):
        for key, value in rdn:
            if key == "organizationName":
                return value
    return ""


def _expiry_finding(cert, now=None):
    not_after = cert.get("notAfter")
    if not not_after:
        return None
    expires = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
    days_left = (expires - (now or datetime.datetime.utcnow())).days
    if days_left < 0:
        return _finding("ssl_expired", f"expired {abs(days_left)} days ago")
    issuer = _issuer_org(cert)
    auto = any(ca in issuer.lower() for ca in AUTO_RENEWING_CAS)
    if days_left <= (AUTO_RENEW_WARN_DAYS if auto else CERT_WARN_DAYS):
        return _finding("ssl_expiring", f"expires in {days_left} days ({issuer or 'unknown issuer'})")
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


def _candidates(url):
    """The addresses worth trying before declaring a site dead: www and bare,
    https and http. www.confident.dental does not resolve; confident.dental
    serves the practice's site, and we told them it was down."""
    parsed = urllib.parse.urlparse(_normalise(url))
    host = parsed.hostname or ""
    hosts = [host]
    hosts.append(host[4:] if host.startswith("www.") else "www." + host)
    out = []
    for scheme in ("https", "http"):
        for h in hosts:
            if h:
                out.append(f"{scheme}://{h}{parsed.path if parsed.path not in ('', '/') else '/'}")
    # A map listing often points at one page of a site. When that page is
    # gone the site usually is not: centri-smile.it answered 200 while its
    # /dentista-milano-affori/ page gave 404, and we had it down as dead.
    if parsed.path not in ("", "/"):
        out += [f"{scheme}://{h}/" for scheme in ("https", "http") for h in hosts if h]
    # The address on file first, then the alternatives.
    listed = _normalise(url)
    return [listed] + [u for u in out if u != listed]


def _resolves(host):
    try:
        socket.getaddrinfo(host, None)
        return True
    except socket.gaierror:
        return False


def _fetch(url):
    """GET the page. Returns (response, chain_broken).

    A missing intermediate certificate fails every script and almost no
    browser: Chrome and Safari fetch the missing piece themselves and show
    the page. www.5rs.it opened normally in a browser while this check
    reported it down. So on that one error, look again without verifying,
    and let the caller record it as the invisible problem it is.
    """
    headers = {"User-Agent": USER_AGENT}
    try:
        return requests.get(url, timeout=SCAN_TIMEOUT, allow_redirects=True, headers=headers), False
    except requests.exceptions.SSLError as e:
        if "unable to get local issuer" not in str(e):
            raise
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return requests.get(url, timeout=SCAN_TIMEOUT, allow_redirects=True,
                            headers=headers, verify=False), True


def check_site(url):
    """Reachability, speed and certificate, over every address the practice
    might actually be reachable at.

    Returns findings; a list whose only codes are severity-0 ones means "we
    could not form a judgement", which is not the same as "nothing wrong".
    """
    url = _normalise(url)
    if not url:
        return [_finding("no_website", "no website on record")]

    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if any(host == s or host.endswith("." + s) for s in SOCIAL_HOSTS):
        # Their "website" is someone else's platform: nothing here is theirs
        # to fix, and its certificate is not theirs either.
        return [_finding("social_only", f"{host} is a social or directory page")]

    attempts, response, final_url, elapsed = [], None, None, None
    chain_broken, answered = False, None
    for candidate in _candidates(url):
        started = time.time()
        try:
            r, chain_broken = _fetch(candidate)
        except requests.exceptions.SSLError as e:
            attempts.append((candidate, f"SSLError {str(e)[:60]}"))
            continue
        except requests.RequestException as e:
            attempts.append((candidate, type(e).__name__))
            continue
        if r.status_code in BLOCKED_STATUS or _is_challenge(r.text):
            print(f"   {candidate}: the site blocked the check ({r.status_code}), no verdict")
            return [_finding("blocked", f"HTTP {r.status_code} to the checker")]
        if r.status_code >= 400:
            # A 404 is not the homepage. We measured one as "does not fit a
            # phone" and queued the claim.
            attempts.append((candidate, f"HTTP {r.status_code}"))
            continue
        response, final_url, elapsed, answered = r, r.url, time.time() - started, candidate
        break

    if response is None:
        detail = "; ".join(f"{u} {why}" for u, why in attempts[:4])
        if not any(_resolves(h) for h in {urllib.parse.urlparse(u).hostname for u, _ in attempts}):
            return [_finding("domain_gone", detail[:160])]
        return [_finding("site_down", detail[:160])]

    findings = []
    listed_path = urllib.parse.urlparse(url).path not in ("", "/")
    if listed_path and urllib.parse.urlparse(answered).path in ("", "/") and attempts:
        findings.append(_finding("listed_page_gone",
                                 f"{url} gives {attempts[0][1]}; the site opens at {answered}"[:160]))
    if chain_broken:
        findings.append(_finding("ssl_chain", "missing intermediate certificate: browsers repair it, scripts fail"))
    # Only judge the certificate of an address the practice actually serves
    # over https. Checking port 443 of a site listed as http reported the
    # hosting provider's certificate as the practice's problem.
    if final_url.startswith("https://"):
        cert_finding = check_certificate(urllib.parse.urlparse(final_url).hostname)
        if cert_finding:
            findings.append(cert_finding)

    if elapsed > SLOW_SECONDS:
        findings.append(_finding("slow", f"{elapsed:.1f}s to download the page from Helsinki"))

    if os.environ.get("SCAN_CHECK_ENGLISH", "0") == "1":
        html = response.text[:200000].lower()
        if 'hreflang="en' not in html and "/en/" not in html and 'lang="en' not in html:
            findings.append(_finding("no_english", "no English version found"))
    return _dedupe(findings)


# Counts the blocks of text a phone visitor would have to scroll sideways to
# read. A page can be wider than the screen for reasons nobody reading it sees:
# on 2026-09-23 a dentist's page was 73px too wide because of one long email
# address in the footer and a cookie banner, and a vet's by 200px because of
# an embedded map - both read perfectly well. Overlays (position fixed, like
# cookie banners and chat bubbles) and anything inside a clipping box (like a
# carousel's off-screen slides) are not counted.
TEXT_PAST_EDGE_JS = """
var vw = document.documentElement.clientWidth, total = 0, out = 0, sample = '';
var all = document.body ? document.body.querySelectorAll('*') : [];
for (var i = 0; i < all.length; i++) {
  var e = all[i], text = false;
  for (var n = e.firstChild; n; n = n.nextSibling) {
    if (n.nodeType === 3 && n.textContent.trim().length > 2) { text = true; break; }
  }
  if (!text) continue;
  var r = e.getBoundingClientRect();
  if (r.width === 0 || r.height === 0 || getComputedStyle(e).visibility === 'hidden') continue;
  var skip = false;
  for (var p = e; p && p !== document.documentElement; p = p.parentElement) {
    var cs = getComputedStyle(p);
    if (cs.position === 'fixed' || cs.position === 'sticky') { skip = true; break; }
    if (p !== e && p !== document.body && ['hidden', 'clip', 'auto', 'scroll'].indexOf(cs.overflowX) >= 0) { skip = true; break; }
  }
  if (skip) continue;
  total++;
  if (r.right > vw + 2 || r.left < -2) {
    out++;
    if (!sample) sample = e.textContent.trim().slice(0, 40);
  }
}
return [total, out, sample];
"""


def _mobile_verdict(has_viewport, overflow, win_width, text_total, text_out, sample=""):
    """not_mobile only when a visitor really has to move the page sideways to
    read it; a page that is merely wider than the screen is mobile_overflow,
    which is recorded but never written to anyone."""
    if not has_viewport:
        return _finding("not_mobile", "no viewport meta tag: phones show the desktop layout")
    if text_out >= 3 and text_out >= 0.1 * text_total:
        return _finding("not_mobile", f"{text_out} of {text_total} blocks of text run past "
                                      f"a {win_width}px phone screen")
    if overflow > 20:
        extra = f', e.g. "{sample}"' if text_out else ", text fits"
        return _finding("mobile_overflow", f"page {overflow}px wider than a {win_width}px "
                                           f"phone screen; {text_out} text block(s) past the edge{extra}")
    return None


def check_mobile(driver, url, shot_path=None):
    """Open the page as a phone does and see whether it fits.

    This used to run in a desktop-shaped window with a desktop user agent, and
    measured the desktop layout. An audit re-checked the 11 leads it had
    flagged: 5 of them fit perfectly well on a phone, and one site even serves
    a separate mobile version that we never saw. Everything here now runs
    under Chrome's device emulation (set in browser()), so "I opened it on a
    phone-sized screen" is a true sentence.
    """
    url = _normalise(url)
    driver.get(url)
    status = driver.execute_script(
        "var n = performance.getEntriesByType('navigation')[0];"
        "return n && n.responseStatus ? n.responseStatus : 0") or 0
    if status >= 400:
        print(f"   {url}: the browser got HTTP {status}, no verdict")
        return None
    body_text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
    if _is_challenge(body_text, driver.title):
        print(f"   {url}: challenge page in the browser, no verdict")
        return None
    time.sleep(2)

    has_viewport = driver.execute_script(
        "return !!document.querySelector('meta[name=\"viewport\"]')")
    # scrollWidth against the layout viewport, both measured inside the
    # emulated phone; innerWidth lies when the page sets its own zoom.
    doc_width = driver.execute_script("return document.documentElement.scrollWidth")
    win_width = driver.execute_script("return document.documentElement.clientWidth")
    text_total, text_out, sample = driver.execute_script(TEXT_PAST_EDGE_JS) or (0, 0, "")
    finding = _mobile_verdict(has_viewport, doc_width - win_width, win_width,
                              text_total, text_out, sample)

    # Only keep the screenshot when it shows something. 102 of the 122 stored
    # shots belonged to leads with no finding, and the app offered them as
    # "proof".
    if shot_path and finding:
        os.makedirs(os.path.dirname(shot_path), exist_ok=True)
        driver.save_screenshot(shot_path)
    return finding


def browser():
    """One headless Chrome for a whole run. Caller closes it."""
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options

    options = Options()
    for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                "--disable-gpu", "--window-size=390,844"):
        options.add_argument(arg)
    # A real phone, not a narrow desktop window: device metrics, touch, and a
    # mobile user agent, so sites that serve a separate mobile version serve
    # us that one too.
    options.add_experimental_option("mobileEmulation", {
        "deviceMetrics": {"width": 390, "height": 844, "pixelRatio": 3.0, "mobile": True},
        "userAgent": MOBILE_UA,
    })
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

    # Do not open a browser on a page the checker was refused, a dead domain
    # or a site that would not answer: the browser gets the same block page,
    # and measuring it is exactly how the first false claim was produced.
    unjudgeable = {"no_website", "site_down", "domain_gone", "blocked", "social_only", "scan_error"}
    if driver and lead.get("website") and not codes & unjudgeable:
        shot = os.path.join(SHOTS_DIR, f"lead-{lead['id']}.png")
        try:
            mobile = check_mobile(driver, lead["website"], shot)
            if mobile:
                findings.append(mobile)
            else:
                shot = None  # nothing to show
        except Exception as e:
            # Record it. Swallowing this is what turned 24 leads "clean"
            # overnight and left no trace anywhere.
            print(f"   mobile check failed for {lead['name']}: {type(e).__name__}: {e}")
            findings.append(_finding("scan_error", f"mobile check: {type(e).__name__}"))
            shot = None

    findings.sort(key=lambda f: -f["severity"])
    return findings, shot


def score(findings):
    """Highest severity wins; ties broken by how much is wrong."""
    if not findings:
        return 0
    return max(f["severity"] for f in findings) * 10 + len(findings)
