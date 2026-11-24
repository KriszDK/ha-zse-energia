"""Import payment and consumption history as long-term statistics.

The portal keeps ~15 years of invoices. Home Assistant sensors only know "now",
so the history is written to the recorder as *external statistics* (cumulative
sums, one point per day with money movement). The statistics graph and
statistic cards can then show yearly/monthly totals with ``stat_types: change``.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .parser import cumulative

try:  # Home Assistant 2025.4+
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:  # pragma: no cover - older cores
    StatisticMeanType = None  # type: ignore[assignment,misc]

_LOGGER = logging.getLogger(__name__)

# series key -> (names per language, unit, unit_class candidates tried in order)
SERIES: dict[str, tuple[dict[str, str], str, tuple[str | None, ...]]] = {
    "advances_paid": (
        {"en": "Advances paid", "hu": "Befizetett előlegek", "sk": "Zaplatené zálohy"},
        "EUR",
        (None,),
    ),
    "settlements_paid": (
        {
            "en": "Settlement surcharges",
            "hu": "Elszámolási pótlék",
            "sk": "Doplatky z vyúčtovania",
        },
        "EUR",
        (None,),
    ),
    "other_paid": (
        {"en": "Other payments", "hu": "Egyéb befizetések", "sk": "Ostatné platby"},
        "EUR",
        (None,),
    ),
    "refunds_received": (
        {"en": "Refunds received", "hu": "Visszautalások", "sk": "Prijaté vrátenia"},
        "EUR",
        (None,),
    ),
    "net_paid": (
        {
            "en": "Net paid",
            "hu": "Nettó fizetés",
            "sk": "Zaplatené netto",
        },
        "EUR",
        (None,),
    ),
    "consumption": (
        {"en": "Consumption", "hu": "Fogyasztás", "sk": "Spotreba"},
        "kWh",
        ("energy", None),
    ),
}


def statistic_id(key: str, zu: str) -> str:
    """e.g. ``zse_energia:advances_paid_6300000001`` (lowercase, digits, underscores)."""
    return f"{DOMAIN}:{key}_{zu}"


def _noon(d: date) -> datetime:
    return dt_util.start_of_local_day(d).replace(hour=12)


def _metadata(
    key: str, zu: str, name: str, unit: str, unit_class: str | None, suffix: bool = False
) -> StatisticMetaData:
    meta: dict[str, Any] = {
        "source": DOMAIN,
        "statistic_id": statistic_id(key, zu),
        # the last digits of the account number only tell several accounts apart
        "name": f"{name} ({zu[-4:]})" if suffix else name,
        "unit_of_measurement": unit,
        "has_sum": True,
        "unit_class": unit_class,
    }
    if StatisticMeanType is not None:
        meta["mean_type"] = StatisticMeanType.NONE
    else:  # pragma: no cover
        meta["has_mean"] = False
    return meta  # type: ignore[return-value]


def async_import_history(
    hass: HomeAssistant, zu: str, history: dict[str, Any], suffix: bool = False
) -> None:
    """(Re)write all statistics of one account. Safe to repeat: rows are upserted by time."""
    lang = hass.config.language.split("-")[0]
    points = dict(history.get("series") or {})
    points["consumption"] = list(history.get("consumption") or [])
    for key, (names, unit, unit_classes) in SERIES.items():
        rows = cumulative(points.get(key) or [])
        if not rows:
            continue
        # a zero baseline just before the first row makes the first period's "change" correct
        stats = [StatisticData(start=_noon(rows[0][0]) - timedelta(hours=1), state=0.0, sum=0.0)]
        stats += [StatisticData(start=_noon(d), state=total, sum=total) for d, _, total in rows]
        error: Exception | None = None
        for unit_class in unit_classes:
            try:
                async_add_external_statistics(
                    hass, _metadata(key, zu, names.get(lang, names["en"]), unit, unit_class, suffix), stats
                )
                error = None
                break
            except HomeAssistantError as err:
                error = err
        if error is not None:
            _LOGGER.warning("Could not import statistics %s: %s", statistic_id(key, zu), error)
