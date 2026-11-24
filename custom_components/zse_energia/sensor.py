"""Sensors for ZSE Energia."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfElectricCurrent, UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ZseConfigEntry, ZseCoordinator
from .entity import PARTNER_SCOPE, ZseEntity
from .hdo import split_code
from .hdo_entity import ZseHdoEntity
from .hdo_manager import STATUS_BUILT_IN, STATUS_ERROR, STATUS_UP_TO_DATE
from .texts import TEXTS, pick_language


@dataclass(frozen=True, kw_only=True)
class ZseSensorDescription(SensorEntityDescription):
    """Sensor with a value (and optional attributes) taken from the parsed account dict."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _settlement(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda a: (a.get("last_settlement") or {}).get(key)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    return None if number is None else int(number)


def _h(*path: str) -> Callable[[dict[str, Any]], Any]:
    """Value from the account's payment history by key path."""

    def fn(a: dict[str, Any]) -> Any:
        v: Any = a.get("history")
        for key in path:
            v = v.get(key) if isinstance(v, dict) else None
        return v

    return fn


def _parts(group: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    return lambda a: {k: _h(group, k)(a) for k in ("advances", "settlements", "other", "refunds")}


def _yearly(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "zse_history": True,
        "since": _h("since")(a),
        "paid_total": _h("totals", "paid")(a),
        "refunds_total": _h("totals", "refunds")(a),
        "yearly": _h("yearly")(a),
    }


def _month_name(a: dict[str, Any]) -> dict[str, Any]:
    d = a.get("next_settlement")
    return {"month": d.strftime("%Y-%m")} if d else {}


EUR = "EUR"

ACCOUNT_SENSORS: tuple[ZseSensorDescription, ...] = (
    ZseSensorDescription(
        key="next_payment_date",
        translation_key="next_payment_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda a: a.get("next_payment_date"),
        attrs_fn=lambda a: {
            "source": a.get("next_payment_source"),
            "payment_method": a.get("payment_method"),
        },
    ),
    ZseSensorDescription(
        key="next_payment_amount",
        translation_key="next_payment_amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=lambda a: a.get("next_payment_amount"),
    ),
    ZseSensorDescription(
        key="next_invoice_date",
        translation_key="next_invoice_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda a: a.get("next_invoice_date"),
    ),
    ZseSensorDescription(
        key="advance_amount",
        translation_key="advance_amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=lambda a: a.get("advance_amount"),
        attrs_fn=lambda a: {"frequency": a.get("advance_frequency")},
    ),
    ZseSensorDescription(
        key="payment_method",
        translation_key="payment_method",
        value_fn=lambda a: a.get("payment_method"),
    ),
    ZseSensorDescription(
        key="tariff",
        translation_key="tariff",
        value_fn=lambda a: a.get("tariff"),
        attrs_fn=lambda a: {
            "product_code": a.get("product_code"),
            "settlement_periodicity": a.get("settlement_periodicity"),
            "measurement_type": a.get("measurement_type"),
            "smart_meter": a.get("smart_meter"),
        },
    ),
    ZseSensorDescription(
        key="advance_due_day",
        translation_key="advance_due_day",
        value_fn=lambda a: a.get("advance_due_day"),
    ),
    ZseSensorDescription(
        key="contract_valid_from",
        translation_key="contract_valid_from",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: a.get("contract_valid_from"),
    ),
    ZseSensorDescription(
        key="distribution_tariff",
        translation_key="distribution_tariff",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: a.get("distribution_tariff"),
    ),
    ZseSensorDescription(
        key="tariffication",
        translation_key="tariffication",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: a.get("tariffication"),
    ),
    ZseSensorDescription(
        key="hdo_code",
        translation_key="hdo_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: a.get("hdo_code"),
    ),
    ZseSensorDescription(
        key="phases",
        translation_key="phases",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: _to_int(a.get("phases")),
    ),
    ZseSensorDescription(
        key="circuit_breaker",
        translation_key="circuit_breaker",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: _to_float(a.get("circuit_breaker_a")),
    ),
    ZseSensorDescription(
        key="distributor",
        translation_key="distributor",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: a.get("distributor"),
    ),
    ZseSensorDescription(
        key="last_settlement_amount",
        translation_key="last_settlement_amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=_settlement("amount"),
        attrs_fn=lambda a: {
            k: v
            for k, v in {
                "invoice": _settlement("invoice")(a),
                "issued": _settlement("date")(a),
                "due": _settlement("due")(a),
                "paid": _settlement("paid")(a),
                "period_from": _settlement("period_from")(a),
                "period_to": _settlement("period_to")(a),
                "open_amount": _settlement("open")(a),
                "note": "negative = credit (overpayment), positive = to pay",
            }.items()
            if v is not None
        },
    ),
    ZseSensorDescription(
        key="last_settlement_date",
        translation_key="last_settlement_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=_settlement("date"),
    ),
    ZseSensorDescription(
        key="next_settlement",
        translation_key="next_settlement",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda a: a.get("next_settlement"),
        attrs_fn=_month_name,
    ),
    ZseSensorDescription(
        key="last_payment_date",
        translation_key="last_payment_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda a: a.get("last_payment_date"),
    ),
    ZseSensorDescription(
        key="consumption_latest_month",
        translation_key="consumption_latest_month",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=0,
        value_fn=lambda a: a.get("consumption_latest_month"),
        attrs_fn=lambda a: {"month_end": a.get("consumption_latest_month_date")},
    ),
    ZseSensorDescription(
        key="consumption_monthly_average",
        translation_key="consumption_monthly_average",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: a.get("consumption_monthly_average"),
    ),
    ZseSensorDescription(
        key="paid_this_year",
        translation_key="paid_this_year",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=_h("this_year", "paid"),
        attrs_fn=_parts("this_year"),
    ),
    ZseSensorDescription(
        key="refunds_this_year",
        translation_key="refunds_this_year",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=_h("this_year", "refunds"),
    ),
    ZseSensorDescription(
        key="paid_total",
        translation_key="paid_total",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_h("totals", "paid"),
        attrs_fn=_parts("totals"),
    ),
    ZseSensorDescription(
        key="refunds_total",
        translation_key="refunds_total",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_h("totals", "refunds"),
    ),
    ZseSensorDescription(
        key="net_paid_total",
        translation_key="net_paid_total",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=_h("totals", "net"),
        attrs_fn=_yearly,
    ),
)

PARTNER_SENSORS: tuple[ZseSensorDescription, ...] = (
    ZseSensorDescription(
        key="to_pay",
        translation_key="to_pay",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=lambda p: p.get("to_pay"),
    ),
    ZseSensorDescription(
        key="overdue",
        translation_key="overdue_amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=lambda p: p.get("overdue"),
    ),
    ZseSensorDescription(
        key="overpayment",
        translation_key="overpayment",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        suggested_display_precision=2,
        value_fn=lambda p: p.get("overpayment"),
    ),
)


class ZseSensor(ZseEntity, SensorEntity):
    """A ZSE value."""

    entity_description: ZseSensorDescription

    def __init__(
        self, coordinator: ZseCoordinator, scope: str, description: ZseSensorDescription
    ) -> None:
        super().__init__(coordinator, scope, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        account = self._account
        return self.entity_description.value_fn(account) if account else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        account = self._account
        if not account:
            return None
        extra = fn(account) if fn else {}
        # "zse_key" lets templates/dashboards find a sensor regardless of its (translated) entity id
        return {"zse_key": self.entity_description.key, **{k: v for k, v in extra.items() if v is not None}}


class ZseLanguageSensor(ZseEntity, SensorEntity):
    """Carries the dashboard texts of the Home Assistant system language (attribute ``t``).

    A dashboard cannot translate its own text, so the ready-made dashboard reads its labels from here.
    """

    _attr_translation_key = "ui_language"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset({"t"})  # a dictionary of ~100 strings: keep it out of the database

    def __init__(self, coordinator: ZseCoordinator) -> None:
        super().__init__(coordinator, PARTNER_SCOPE, "ui")

    @property
    def native_value(self) -> str:
        return pick_language(self.hass.config.language)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"zse_key": "ui", "t": TEXTS[self.native_value]}


class ZseNextTariffChangeSensor(ZseHdoEntity, SensorEntity):
    """When the tariff switches next (low -> high or high -> low)."""

    _attr_translation_key = "next_tariff_change"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: ZseCoordinator, zu: str) -> None:
        super().__init__(coordinator, zu, "next_tariff_change")

    @property
    def native_value(self) -> Any:
        snap = self._snapshot()
        return snap.changes_at if snap else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"zse_key": "next_tariff_change"}


class ZseHighTariffHoursSensor(ZseHdoEntity, SensorEntity):
    """Hours of high tariff in today's schedule."""

    _attr_translation_key = "high_tariff_hours_today"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: ZseCoordinator, zu: str) -> None:
        super().__init__(coordinator, zu, "high_tariff_hours_today")

    @property
    def native_value(self) -> float | None:
        snap = self._snapshot()
        return snap.high_hours_today if snap else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"zse_key": "high_tariff_hours_today"}


class ZseHdoDataSensor(ZseEntity, SensorEntity):
    """Where the low/high tariff table comes from: downloaded, built-in copy, or the last download failed."""

    _attr_translation_key = "hdo_data"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [STATUS_UP_TO_DATE, STATUS_BUILT_IN, STATUS_ERROR]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ZseCoordinator) -> None:
        super().__init__(coordinator, PARTNER_SCOPE, "hdo_data")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.hdo.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> str:
        return self.coordinator.hdo.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        hdo = self.coordinator.hdo
        return {
            "zse_key": "hdo_data",
            "downloaded_at": hdo.downloaded_at.isoformat() if hdo.downloaded_at else None,
            "last_attempt": hdo.last_attempt.isoformat() if hdo.last_attempt else None,
            "error": hdo.error,
            "programs": len(hdo.programs),
        }


def _has_hdo(account: dict[str, Any]) -> bool:
    return bool(split_code(account.get("hdo_code")))


async def async_setup_entry(
    hass: HomeAssistant, entry: ZseConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [ZseSensor(coordinator, PARTNER_SCOPE, d) for d in PARTNER_SENSORS]
    entities.append(ZseLanguageSensor(coordinator))
    accounts = (coordinator.data or {}).get("accounts", {})
    if any(_has_hdo(a) for a in accounts.values()):
        entities.append(ZseHdoDataSensor(coordinator))
    for zu, account in accounts.items():
        entities += [ZseSensor(coordinator, zu, d) for d in ACCOUNT_SENSORS]
        if _has_hdo(account):
            entities += [ZseNextTariffChangeSensor(coordinator, zu), ZseHighTariffHoursSensor(coordinator, zu)]
    async_add_entities(entities)
