"""Binary sensors for ZSE Energia."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import ZseConfigEntry, ZseCoordinator
from .entity import PARTNER_SCOPE, ZseEntity
from .hdo import split_code
from .hdo_entity import ZseHdoEntity


class ZseOverdueBinarySensor(ZseEntity, BinarySensorEntity):
    """On when something is past its due date."""

    _attr_translation_key = "overdue"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: ZseCoordinator) -> None:
        super().__init__(coordinator, PARTNER_SCOPE, "overdue_flag")

    @property
    def is_on(self) -> bool | None:
        account = self._account
        if not account or account.get("overdue") is None:
            return None
        return account["overdue"] > 0


class ZsePaymentPendingBinarySensor(ZseEntity, BinarySensorEntity):
    """On while an issued invoice is waiting to be paid (a direct debit may still collect it)."""

    _attr_translation_key = "payment_pending"

    def __init__(self, coordinator: ZseCoordinator, zu: str) -> None:
        super().__init__(coordinator, zu, "payment_pending")

    @property
    def is_on(self) -> bool | None:
        account = self._account
        return None if account is None else account.get("open_invoices", 0) > 0


class ZseEInvoiceBinarySensor(ZseEntity, BinarySensorEntity):
    """On when electronic invoices are enabled for the account."""

    _attr_translation_key = "e_invoice"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ZseCoordinator, zu: str) -> None:
        super().__init__(coordinator, zu, "e_invoice")

    @property
    def is_on(self) -> bool | None:
        account = self._account
        return None if account is None else account.get("e_invoice")


class ZseLowTariffBinarySensor(ZseHdoEntity, BinarySensorEntity):
    """On while the low tariff (nízka tarifa) is active at the meter, off during the high tariff."""

    _attr_translation_key = "low_tariff"

    def __init__(self, coordinator: ZseCoordinator, zu: str) -> None:
        super().__init__(coordinator, zu, "low_tariff")

    @property
    def is_on(self) -> bool | None:
        snap = self._snapshot()
        return snap.low if snap else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"zse_key": "low_tariff", "programs": self._programs}
        snap = self._snapshot()
        if snap is None:
            return attrs
        now = dt_util.now()

        def local(moment: Any) -> str | None:
            if moment is None:
                return None
            moment = dt_util.as_local(moment)
            return moment.strftime("%H:%M") if moment.date() == now.date() else moment.strftime("%m-%d %H:%M")

        attrs.update(
            changes_at=snap.changes_at.isoformat() if snap.changes_at else None,
            changes_at_local=local(snap.changes_at),
            next_low_start=snap.next_low_start.isoformat() if snap.next_low_start else None,
            next_low_end=snap.next_low_end.isoformat() if snap.next_low_end else None,
            low_windows_today=list(snap.low_today),
            high_windows_today=list(snap.high_today),
            high_windows_tomorrow=list(snap.high_tomorrow),
            high_hours_today=snap.high_hours_today,
        )
        return attrs


async def async_setup_entry(
    hass: HomeAssistant, entry: ZseConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    entities: list[ZseEntity] = [ZseOverdueBinarySensor(coordinator)]
    for zu, account in (coordinator.data or {}).get("accounts", {}).items():
        entities += [ZsePaymentPendingBinarySensor(coordinator, zu), ZseEInvoiceBinarySensor(coordinator, zu)]
        if split_code(account.get("hdo_code")):
            entities.append(ZseLowTariffBinarySensor(coordinator, zu))
    async_add_entities(entities)
