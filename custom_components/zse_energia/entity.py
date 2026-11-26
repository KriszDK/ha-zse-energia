"""Base entities for ZSE Energia."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZseCoordinator

PARTNER_SCOPE = "partner"


class ZseEntity(CoordinatorEntity[ZseCoordinator]):
    """Entity bound to one contract account (``scope`` = its number) or to the whole partner."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZseCoordinator, scope: str, key: str) -> None:
        super().__init__(coordinator)
        self._scope = scope
        self._zse_key = key
        partner = coordinator.client.partner or ""
        if scope == PARTNER_SCOPE:
            ident, name = f"{DOMAIN}_{partner}", "ZSE account"
        else:
            ident = f"{DOMAIN}_{scope}"
            name = (self._account or {}).get("device_name") or f"ZSE {scope}"
        self._attr_unique_id = f"{ident}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ident)},
            name=name,
            manufacturer="ZSE",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _account(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        if self._scope == PARTNER_SCOPE:
            return data.get("partner")
        return (data.get("accounts") or {}).get(self._scope)

    @property
    def _kinds(self) -> list[str]:
        """Commodities this entity is about: ``["electricity"]``, ``["gas"]`` ... (partner level: all of its accounts)."""
        data = self.coordinator.data or {}
        if self._scope == PARTNER_SCOPE:
            return sorted({a["kind"] for a in (data.get("accounts") or {}).values() if a.get("kind")})
        return [(self._account or {}).get("kind") or "other"]

    @property
    def _zse_attrs(self) -> dict[str, Any]:
        # lets templates/dashboards find an entity regardless of its (translated) entity id and tell
        # electricity from gas when several accounts are set up
        return {"zse_key": self._zse_key, "zse_kinds": self._kinds}

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self._zse_attrs

    @property
    def available(self) -> bool:
        return super().available and self._account is not None
