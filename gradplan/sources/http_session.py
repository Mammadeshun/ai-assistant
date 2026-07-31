"""HTTP transport for the authenticated sources.

Playwright is the primary transport, but a headless browser cannot always
reach the network (locked-down CI, egress proxies that only tunnel CONNECT for
non-browser clients). This module speaks the same small interface as
``browser.Session`` — ``login`` and ``goto`` — over plain HTTP with a cookie
jar, so the scrapers work either way.

It implements the UniPV Shibboleth SAML2 flow used by Esse3 and Kiro:

    Esse3 -> unipv.idp.cineca.it session probe (auto-submit)
          -> login-method routing form (pick the username/password flow)
          -> credential form (j_username / j_password)
          -> SAML assertion posted back to the service provider

Every step is a form the browser would auto-submit; here they are submitted
explicitly. Only one credential attempt is ever made per login, so a wrong
password cannot turn into a lockout loop.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html import unescape
from http.cookiejar import CookieJar
from typing import Any
import re

from .. import config
from ..archive import ArchivedResponse, RawArchive
from .browser import LoginError

# The IdP's own init.js maps the login-method buttons onto these hidden fields:
#   triggerFlow(flow, id, selectedFlow):
#       spid_idp      = id
#       auth_ctx      = 'authn/' + flow
#       selected_flow = selectedFlow
# The username/password button calls triggerFlow('Password', '', 'internal').
PASSWORD_FLOW = {
    "spid_idp": "",
    "auth_ctx": "authn/Password",
    "selected_flow": "internal",
}

MAX_HOPS = 12


@dataclass
class Form:
    action: str
    method: str
    fields: dict[str, str]
    has_password: bool
    element_id: str = ""

    @property
    def is_routing(self) -> bool:
        return "selected_flow" in self.fields

    @property
    def is_saml(self) -> bool:
        return "SAMLResponse" in self.fields or "SAMLRequest" in self.fields


def parse_forms(markup: str) -> list[Form]:
    forms: list[Form] = []
    for match in re.finditer(r"<form([^>]*)>(.*?)</form>", markup, re.S | re.I):
        attrs, body = match.group(1), match.group(2)
        action = re.search(r'action="([^"]*)"', attrs, re.I)
        method = re.search(r'method="([^"]*)"', attrs, re.I)
        element_id = re.search(r'id="([^"]*)"', attrs, re.I)

        fields: dict[str, str] = {}
        has_password = False
        for tag in re.finditer(r"<(?:input|textarea)[^>]*>", body, re.I):
            raw = tag.group(0)
            name = re.search(r'name="([^"]*)"', raw, re.I)
            value = re.search(r'value="([^"]*)"', raw, re.I)
            kind = re.search(r'type="([^"]*)"', raw, re.I)
            if kind and kind.group(1).lower() == "password":
                has_password = True
            if kind and kind.group(1).lower() == "submit" and not name:
                continue
            if name:
                fields[name.group(1)] = unescape(value.group(1)) if value else ""

        # The IdP's submit control is a <button name="_eventId_proceed">, and
        # Spring Webflow will simply re-render the form without that event.
        # A browser sends the button that was clicked, so send the first named
        # one — sending them all would fire conflicting events.
        for tag in re.finditer(r"<button([^>]*)>", body, re.I):
            attrs = tag.group(1)
            kind = re.search(r'type="([^"]*)"', attrs, re.I)
            if kind and kind.group(1).lower() not in ("submit", ""):
                continue
            name = re.search(r'name="([^"]*)"', attrs, re.I)
            if not name or name.group(1) in fields:
                continue
            value = re.search(r'value="([^"]*)"', attrs, re.I)
            fields[name.group(1)] = unescape(value.group(1)) if value else ""
            break
        forms.append(
            Form(
                action=unescape(action.group(1)) if action else "",
                method=(method.group(1) if method else "get").lower(),
                fields=fields,
                has_password=has_password,
                element_id=element_id.group(1) if element_id else "",
            )
        )
    return forms


class HttpSession:
    """Cookie-jar HTTP client with the same surface the scrapers expect."""

    def __init__(
        self,
        archive: RawArchive,
        *,
        delay: float | None = None,
        credentials: config.Credentials | None = None,
    ) -> None:
        self.archive = archive
        self.delay = config.REQUEST_DELAY_SECONDS if delay is None else delay
        self.credentials = credentials
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )
        self.opener.addheaders = [("User-Agent", config.USER_AGENT)]
        self.url = ""
        self.content = ""

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> "HttpSession":
        return self

    def close(self) -> None:
        pass

    # -- primitives ---------------------------------------------------------
    def _request(self, url: str, data: dict[str, str] | None = None) -> tuple[str, str, int]:
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        request = urllib.request.Request(url, data=body)
        if self.url:
            request.add_header("Referer", self.url)
        try:
            with self.opener.open(request, timeout=60) as response:
                text = response.read().decode("utf-8", errors="replace")
                return response.url, text, response.status
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return exc.url, text, exc.code

    def _submit(self, form: Form, overrides: dict[str, str] | None = None) -> None:
        target = urllib.parse.urljoin(self.url, form.action) if form.action else self.url
        fields = dict(form.fields)
        if overrides:
            fields.update(overrides)
        if form.method == "get":
            target = f"{target}?{urllib.parse.urlencode(fields)}"
            self.url, self.content, _ = self._request(target)
        else:
            self.url, self.content, _ = self._request(target, fields)
        time.sleep(self.delay)

    # -- interface used by the scrapers -------------------------------------
    def goto(self, url: str, *, source: str, label: str) -> ArchivedResponse:
        self.url, self.content, status = self._request(url)
        record = self.archive.save(
            source=source,
            label=label,
            url=self.url,
            payload=self.content,
            kind="html",
            status=status,
        )
        time.sleep(self.delay)
        return record

    def post_json(
        self, url: str, payload: Any, *, source: str, label: str
    ) -> ArchivedResponse:
        """POST a JSON body and archive the JSON response."""
        import json as _json

        body = _json.dumps(payload).encode()
        request = urllib.request.Request(url, data=body)
        request.add_header("Content-Type", "application/json")
        if self.url:
            request.add_header("Referer", self.url)
        try:
            with self.opener.open(request, timeout=60) as response:
                text = response.read().decode("utf-8", errors="replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            status = exc.code
        record = self.archive.save(
            source=source, label=label, url=url, payload=text, kind="json", status=status
        )
        time.sleep(self.delay)
        return record

    def login(self, entry_url: str, *, success_marker: str) -> None:
        """Walk the SSO chain until an authenticated page is reached."""
        self.url, self.content, _ = self._request(entry_url)
        credentials_sent = False

        for _ in range(MAX_HOPS):
            if self._authenticated(success_marker):
                return

            forms = parse_forms(self.content)
            if not forms:
                break

            credential_form = next((f for f in forms if f.has_password), None)
            if credential_form is not None:
                if credentials_sent:
                    # Back at the login form after submitting once: the
                    # credentials were rejected. Stop rather than retry.
                    break
                if self.credentials is None:
                    raise LoginError(
                        "Reached the UniPV login form but no credentials were "
                        "supplied. Set UNIPV_USERNAME and UNIPV_PASSWORD."
                    )
                self._submit(
                    credential_form,
                    {
                        "j_username": self.credentials.username,
                        "j_password": self.credentials.password,
                    },
                )
                credentials_sent = True
                continue

            routing = next((f for f in forms if f.is_routing), None)
            if routing is not None:
                self._submit(routing, PASSWORD_FLOW)
                continue

            saml = next((f for f in forms if f.is_saml), None)
            self._submit(saml or forms[0])

        if self._authenticated(success_marker):
            return

        self.archive.save(
            source="debug",
            label="login-failed",
            url=self.url,
            payload=self.content,
            kind="html",
        )
        raise LoginError(
            f"Login did not reach an authenticated page (stopped at {self.url}). "
            "The last page was archived under data/raw/debug/. "
            + self._failure_hint()
        )

    def _authenticated(self, success_marker: str) -> bool:
        low_url = self.url.lower()
        if "idp.cineca.it" in low_url or "logon.do" in low_url:
            return False
        return success_marker.lower() in low_url or success_marker.lower() in self.content.lower()

    def _failure_hint(self) -> str:
        text = re.sub(r"<[^>]+>", " ", self.content)
        text = unescape(re.sub(r"\s+", " ", text))
        for pattern in (
            r"(credenziali[^.]{0,80})",
            r"(username o password[^.]{0,80})",
            r"(bad credentials[^.]{0,80})",
            r"(account[^.]{0,60}(bloccat|lock)[^.]{0,60})",
        ):
            found = re.search(pattern, text, re.I)
            if found:
                return f"The page said: {found.group(1).strip()!r}"
        return ""


def http_session(
    archive: RawArchive,
    *,
    delay: float | None = None,
) -> HttpSession:
    return HttpSession(
        archive, delay=delay, credentials=config.Credentials.from_env()
    ).start()
