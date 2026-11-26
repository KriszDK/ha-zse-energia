"""Diagnostics for ZSE Energia (everything personal is redacted)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_EMAIL, CONF_PARTNER, CONF_PASSWORD
from .coordinator import ZseConfigEntry

TO_REDACT_ENTRY = {CONF_EMAIL, CONF_PASSWORD, CONF_PARTNER, "unique_id", "title"}
TO_REDACT_DATA = {"zu", "device_name", "invoice", "hdo_code", "history"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ZseConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data.data or {}
    accounts = [async_redact_data(a, TO_REDACT_DATA) for a in (data.get("accounts") or {}).values()]
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT_ENTRY),
        "partner": data.get("partner"),
        "accounts": accounts,
    }
