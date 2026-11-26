"""Client for the ZSE customer portal (www.zse.sk).

Unofficial: the portal has no public API. This replays what the web app does:
sign in through Azure AD B2C with an e-mail account, exchange the authorization
code for the portal's own bearer token, then call the read-only JSON methods
(``POST /japi/<Service>/<method>`` with positional-argument arrays).

No Home Assistant imports here, so it can be tested stand-alone.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import aiohttp
from yarl import URL

from .const import B2C_HOST, B2C_PROVIDER_ID, DATA_SERVICE, SITE_URL, USER_AGENT
from .parser import active_contracts

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)
_SETTINGS_RE = re.compile(r"var SETTINGS = (\{.*?\});\s*</script>", re.S)
_TOKEN_MARGIN = 300  # renew the token this many seconds before it expires
_PAGE_SIZE = 50
_MAX_PAGES = 6
# never sent anywhere but the HTTPS origin they were meant for (see _redirect_headers)
_SENSITIVE_HEADERS = frozenset({"authorization", "x-csrf-token"})


class ZseError(Exception):
    """Base error."""


class ZseAuthError(ZseError):
    """Credentials rejected, or the sign-in needs a step we cannot do (MFA/captcha)."""


class ZseConnectionError(ZseError):
    """Network problem."""


class ZseApiError(ZseError):
    """The portal answered with an error status."""

    def __init__(self, status: int, text: str) -> None:
        super().__init__(f"HTTP {status}: {text}")
        self.status = status


def _settings(html: str) -> dict[str, Any]:
    match = _SETTINGS_RE.search(html)
    if not match:
        raise ZseError("Unexpected B2C page (no SETTINGS block); the portal layout may have changed")
    return json.loads(match.group(1))


def _jwt_exp(token: str) -> float | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload)).get("exp")
        if exp is None:
            return None
        return exp / 1000 if exp > 10_000_000_000 else float(exp)
    except (IndexError, ValueError):
        return None


def _redirect_headers(headers: dict[str, str], src: URL, dst: URL) -> dict[str, str]:
    """Headers to keep when following a redirect from ``src`` to ``dst``.

    The bearer token and the CSRF token stay only on the same HTTPS origin; a redirect to
    another host or to plain HTTP gets the request without them.
    """
    if dst.scheme == "https" and dst.origin() == src.origin():
        return dict(headers)
    return {k: v for k, v in headers.items() if k.lower() not in _SENSITIVE_HEADERS}


class ZseClient:
    """Signs in and calls the portal API.

    Cookies are handled here, not by the session: aiohttp's cookie jar re-quotes
    cookie values containing ``=``, and Azure B2C rejects the quoted form
    (HTTP 400). Pass a session that does not store cookies itself, e.g.
    ``aiohttp.DummyCookieJar()``.
    """

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None
        self._expires = 0.0
        self._lock = asyncio.Lock()
        self._cookies: dict[str, dict[str, str]] = {}  # host -> name -> raw value
        self.partner: str | None = None

    # ------------------------------------------------------------------ http
    def _cookie_header(self, url: URL) -> str | None:
        if url.scheme != "https":  # the sign-in cookies never travel unencrypted
            return None
        jar = self._cookies.get(url.host or "", {})
        return "; ".join(f"{k}={v}" for k, v in jar.items()) or None

    def _store_cookies(self, url: URL, headers: Any) -> None:
        jar = self._cookies.setdefault(url.host or "", {})
        for line in headers.getall("Set-Cookie", []):
            pair = line.split(";", 1)[0]
            name, sep, value = pair.partition("=")
            if not sep:
                continue
            if re.search(r"max-age=0|expires=\w{3}, 01[ -]jan[ -]1970", line, re.I):
                jar.pop(name.strip(), None)
            else:
                jar[name.strip()] = value.strip()

    async def _request(
        self, method: str, url: str | URL, *, follow: bool = True, **kwargs: Any
    ) -> tuple[int, Any, str]:
        """One HTTP exchange; redirects are followed by hand so cookies are kept raw."""
        url = url if isinstance(url, URL) else URL(url)
        extra_headers = kwargs.pop("headers", {})
        for _ in range(10):
            headers = {"User-Agent": USER_AGENT, **extra_headers}
            if cookie := self._cookie_header(url):
                headers["Cookie"] = cookie
            try:
                async with self._session.request(
                    method, url, headers=headers, timeout=_TIMEOUT, allow_redirects=False, **kwargs
                ) as resp:
                    self._store_cookies(url, resp.headers)
                    status, resp_headers, text = resp.status, resp.headers, await resp.text()
            except (aiohttp.ClientError, TimeoutError) as err:
                raise ZseConnectionError(str(err)) from err
            location = resp_headers.get("Location")
            if follow and status in (301, 302, 303, 307, 308) and location:
                nxt = URL(location, encoded=True)
                nxt = nxt if nxt.is_absolute() else url.join(nxt)
                extra_headers = _redirect_headers(extra_headers, url, nxt)
                url = nxt
                method, kwargs = "GET", {}
                continue
            return status, resp_headers, text
        raise ZseError("Too many redirects")

    # ----------------------------------------------------------------- login
    async def _start_signin(self) -> tuple[dict[str, Any], str]:
        """Open B2C, pick the e-mail provider; return (SelfAsserted page settings, page url)."""
        _, _, text = await self._request("GET", f"{SITE_URL}/b2c/login")
        st = _settings(text)
        tenant, policy = st["hosts"]["tenant"], st["hosts"]["policy"]
        url = (
            f"{B2C_HOST}{tenant}/api/ClaimsProviderSelection/selected"
            f"?accountId={B2C_PROVIDER_ID}&csrf_token={st['csrf']}&tx={st['transId']}&p={policy}"
        )
        _, _, text = await self._request("GET", URL(url, encoded=True))
        st = _settings(text)
        if st.get("api") != "SelfAsserted":
            raise ZseError(f"Unexpected B2C step {st.get('api')!r}; expected the e-mail form")
        return st, url

    async def async_login(self) -> None:
        """Run the full sign-in and store the bearer token."""
        self._cookies.clear()
        st, page_url = await self._start_signin()
        tenant, policy = st["hosts"]["tenant"], st["hosts"]["policy"]
        tx, csrf = st["transId"], st["csrf"]

        _, _, text = await self._request(
            "POST",
            URL(f"{B2C_HOST}{tenant}/SelfAsserted?tx={tx}&p={policy}", encoded=True),
            data={"request_type": "RESPONSE", "signInName": self._email, "password": self._password},
            headers={
                "X-CSRF-TOKEN": csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": B2C_HOST,
                "Referer": page_url,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
        )
        try:
            body = json.loads(text)
        except ValueError as err:
            raise ZseError("Unexpected sign-in response") from err
        if str(body.get("status")) != "200":
            raise ZseAuthError(body.get("message") or "Sign-in rejected")

        status, headers, _ = await self._request(
            "GET",
            URL(
                f"{B2C_HOST}{tenant}/api/SelfAsserted/confirmed?csrf_token={csrf}&tx={tx}&p={policy}",
                encoded=True,
            ),
            follow=False,
        )
        location = headers.get("Location", "")
        query = parse_qs(urlparse(location).query)
        if "code" not in query:
            raise ZseAuthError("Sign-in needs an extra step (MFA/captcha?) that is not supported")

        status, _, text = await self._request("GET", f"{SITE_URL}/b2c/code", params={"code": query["code"][0]})
        if status != 200:
            raise ZseError(f"Code exchange failed (HTTP {status})")
        try:
            data = json.loads(text)
        except ValueError as err:
            raise ZseError("Code exchange returned no JSON") from err

        token = data.get("jwt")
        if not isinstance(token, str):
            raise ZseError("No token in the sign-in response")
        self._token = token
        expire = data.get("expire")
        if isinstance(expire, (int, float)):
            self._expires = expire / 1000 if expire > 10_000_000_000 else float(expire)
        else:
            self._expires = _jwt_exp(token) or time.time() + 3600
        self.partner = self._find_partner(data)
        if not self.partner:
            raise ZseError("No partner number in the sign-in response")

    @staticmethod
    def _find_partner(data: dict[str, Any]) -> str | None:
        candidates = [p for p in data.get("partners") or [] if isinstance(p, str)]
        for p in (data.get("userData") or {}).get("partners") or []:
            if isinstance(p, dict):
                candidates.append(str(p.get("partnerCode") or ""))
        return next((c for c in candidates if re.fullmatch(r"\d{10}", c)), None)

    async def _ensure_token(self) -> None:
        async with self._lock:
            if not self._token or time.time() > self._expires - _TOKEN_MARGIN:
                await self.async_login()

    # ------------------------------------------------------------------ calls
    async def async_call(
        self, service: str, method: str, args: list[Any], *, _retry: bool = True
    ) -> Any:
        """Call ``/japi/<service>/<method>`` with positional arguments."""
        await self._ensure_token()
        status, _, text = await self._request(
            "POST",
            f"{SITE_URL}/japi/{service}/{method}",
            json=args,
            headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
        )
        if status in (401, 403) and _retry:
            self._token = None
            return await self.async_call(service, method, args, _retry=False)
        if status in (401, 403):
            raise ZseAuthError(f"{method}: access denied (HTTP {status})")
        if status != 200:
            raise ZseApiError(status, text[:200])
        return json.loads(text) if text else None


# ----------------------------------------------------------------------- fetch
async def _optional(coro: Any) -> Any:
    """Await a nice-to-have call; API errors just mean 'no data'."""
    try:
        return await coro
    except ZseApiError as err:
        _LOGGER.debug("Optional ZSE call failed: %s", err)
        return None


async def _paged_invoices(client: ZseClient) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for page in range(1, _MAX_PAGES + 1):
        chunk = await client.async_call(
            DATA_SERVICE,
            "getStavUctuFaktury",
            [{"cisloOP": client.partner, "pageSize": _PAGE_SIZE, "page": page}],
        )
        if not chunk:
            break
        first = str(chunk[0].get("id"))
        if first in seen:
            break
        seen.add(first)
        out += chunk
    return out


async def async_fetch_raw(client: ZseClient) -> dict[str, Any]:
    """Collect everything the sensors need (read-only calls)."""
    p = client.partner
    call = client.async_call
    zucty = await call(DATA_SERVICE, "getZmluvneUcty", [p])
    vztahy = await call(DATA_SERVICE, "getZmluvneVztahy", [p])
    rozpisy = await call(DATA_SERVICE, "getRozpisyZaloh", [p])
    zostatok = await call(DATA_SERVICE, "getPohladavkyZostatok", [p])
    faktury = await _optional(_paged_invoices(client))

    om_detail: dict[str, Any] = {}
    spotreba: dict[str, Any] = {}
    for zu, contract in active_contracts(vztahy).items():
        om = str(contract["odberneMiestoCislo"])
        om_detail[om] = await _optional(call(DATA_SERVICE, "getOdberneMiestoDetail", [p, om]))
        data = await _optional(call(DATA_SERVICE, "spotrebaOM", [p, zu, om, 1]))
        spotreba[zu] = data.get("spotrebaData") if isinstance(data, dict) else None

    return {
        "zucty": zucty,
        "vztahy": vztahy,
        "rozpisy": rozpisy,
        "zostatok": zostatok,
        "faktury": faktury,
        "om_detail": om_detail,
        "spotreba": spotreba,
    }
