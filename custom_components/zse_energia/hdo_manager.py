"""Keeps the ZSDIS low/high tariff tables.

The tables are downloaded from the ZSDIS page about once a month, stored in Home Assistant's storage and
read from there after a restart. A copy shipped with the integration (``hdo_programs.json``) is the last
resort: if the page cannot be read or has changed, the previous data stays in use and the "HDO data" sensor
says so. The tariff switching times themselves are computed locally, not polled.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, USER_AGENT
from .hdo import PAGE_URL, HdoParseError, extract_rates, tariff_intervals

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
REFRESH_EVERY = timedelta(days=30)
RETRY_EVERY = timedelta(days=1)
BUNDLED = Path(__file__).with_name("hdo_programs.json")

STATUS_UP_TO_DATE = "up_to_date"
STATUS_BUILT_IN = "built_in"
STATUS_ERROR = "error"


def _load_bundled() -> list[dict[str, Any]]:
    return json.loads(BUNDLED.read_text(encoding="utf-8"))["programs"]


class HdoManager:
    """Holds the programs, refreshes them monthly and tells entities when they changed."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, f"{DOMAIN}.hdo")
        self.builtin: list[dict[str, Any]] = []
        self.programs: list[dict[str, Any]] = []
        self.downloaded_at: datetime | None = None  # None: the built-in copy is in use
        self.last_attempt: datetime | None = None
        self.error: str | None = None
        self._listeners: list[Callable[[], None]] = []

    # ---------------------------------------------------------------------------------------- state
    @property
    def status(self) -> str:
        if self.error:
            return STATUS_ERROR
        return STATUS_BUILT_IN if self.downloaded_at is None else STATUS_UP_TO_DATE

    def intervals_for(self, hdo_code: Any) -> list[dict[str, Any]]:
        """Low-tariff windows for a meter code; the built-in copy fills in if the downloaded one lacks the code."""
        return tariff_intervals(self.programs, hdo_code) or tariff_intervals(self.builtin, hdo_code)

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    # --------------------------------------------------------------------------------------- loading
    async def async_load(self) -> None:
        """Built-in copy first, then whatever an earlier download left in storage."""
        self.builtin = await self.hass.async_add_executor_job(_load_bundled)
        self.programs = self.builtin
        stored = await self._store.async_load()
        if stored and isinstance(stored.get("programs"), list) and len(stored["programs"]) >= 10:
            self.programs = stored["programs"]
            self.downloaded_at = dt_util.parse_datetime(stored.get("downloaded", ""))

    async def async_refresh_if_due(self, _now: datetime | None = None) -> None:
        """Download again when the data is older than a month (and retry a failed download daily)."""
        now = dt_util.utcnow()
        if self.downloaded_at and now - self.downloaded_at < REFRESH_EVERY and not self.error:
            return
        if self.last_attempt and now - self.last_attempt < RETRY_EVERY:
            return
        await self.async_refresh()

    async def async_refresh(self) -> None:
        self.last_attempt = dt_util.utcnow()
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                PAGE_URL,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "sk,en;q=0.5"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                html = await response.text()
            programs = extract_rates(html)
        except (aiohttp.ClientError, TimeoutError, HdoParseError) as err:
            self.error = f"{type(err).__name__}: {err}"
            _LOGGER.warning(
                "Could not update the ZSDIS low/high tariff table (%s); keeping the %s data",
                self.error,
                "downloaded" if self.downloaded_at else "built-in",
            )
            self._notify()
            return
        self.programs = programs
        self.downloaded_at = self.last_attempt
        self.error = None
        await self._store.async_save({"downloaded": self.downloaded_at.isoformat(), "programs": programs})
        _LOGGER.debug("ZSDIS low/high tariff table updated (%d programs)", len(programs))
        self._notify()
