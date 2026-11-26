"""Data update coordinator for ZSE Energia."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ZseAuthError, ZseClient, ZseError, async_fetch_raw
from .const import CONF_SCAN_HOURS, DEFAULT_SCAN_HOURS, DOMAIN
from .hdo_manager import HdoManager
from .parser import build
from .statistics import async_import_history, async_import_total

_LOGGER = logging.getLogger(__name__)

ZseConfigEntry = ConfigEntry["ZseCoordinator"]


class ZseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the ZSE portal (a few times a day is plenty for billing data)."""

    config_entry: ZseConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ZseConfigEntry, client: ZseClient) -> None:
        hours = entry.options.get(CONF_SCAN_HOURS, DEFAULT_SCAN_HOURS)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(hours=hours),
        )
        self.client = client
        self.hdo = HdoManager(hass)
        self._reset_done = False

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            raw = await async_fetch_raw(self.client)
        except ZseAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ZseError as err:
            raise UpdateFailed(str(err)) from err
        data = build(raw, dt_util.now().date())
        several = len(data["accounts"]) > 1
        for zu, account in data["accounts"].items():
            async_import_history(
                self.hass,
                zu,
                account["history"],
                suffix=several,
                kind=account.get("kind", "electricity"),
                reset_gas_consumption=not self._reset_done,
            )
        self._reset_done = True
        self._import_total(data)
        return data

    def _import_total(self, own: dict[str, Any]) -> None:
        """Net payments of all contract accounts of all ZSE logins added together (own data is the fresh one)."""
        histories = [a["history"] for a in own["accounts"].values()]
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            other = getattr(entry, "runtime_data", None)
            if other is not None and other is not self and getattr(other, "data", None):
                histories += [a["history"] for a in other.data["accounts"].values()]
        if len(histories) > 1:
            async_import_total(self.hass, histories)
