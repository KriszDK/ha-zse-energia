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
from .const import CONF_SCAN_HOURS, CONF_STAT_NUMBER, DEFAULT_SCAN_HOURS, DOMAIN
from .hdo_manager import HdoManager
from .parser import build
from .stat_ids import numbers_needed
from .statistics import async_import_history, async_import_total, async_remove_obsolete

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
        self._cleaned = False

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            raw = await async_fetch_raw(self.client)
        except ZseAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ZseError as err:
            raise UpdateFailed(str(err)) from err
        data = build(raw, dt_util.now().date())
        several = len(data["accounts"]) > 1
        # the account number is part of the statistic ids when the option says so, and always when
        # one login has several accounts of the same kind (they would overwrite each other otherwise)
        option = bool(self.config_entry.options.get(CONF_STAT_NUMBER, False))
        forced = numbers_needed(data["accounts"])
        for zu, account in data["accounts"].items():
            kind = account.get("kind", "electricity")
            with_number = option or zu in forced
            if not self._cleaned:  # once per start: statistics of older naming schemes
                async_remove_obsolete(self.hass, zu, kind, with_number)
            async_import_history(
                self.hass, zu, account["history"], suffix=several, kind=kind, with_number=with_number
            )
        self._cleaned = True
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
