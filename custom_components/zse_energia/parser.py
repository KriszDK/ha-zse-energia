"""Turn raw ZSE portal responses into plain sensor values.

Pure Python (no Home Assistant imports) so it can be unit-tested offline.
All portal field names are Slovak; the output keys are English.
"""
from __future__ import annotations

from datetime import date
from statistics import mean
from typing import Any

STAV_UKONCENY = 4  # contract status "ukončený" (terminated)
TYP_SETTLEMENT = 3  # "Faktúra vyúčtovacia" (annual settlement invoice)
PAYMENT_RECEIVED = 1  # "Prijatá platba"


def _d(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _label(obj: Any) -> str | None:
    """Human-readable text of a portal code object.

    The portal wraps codes as ``{"id": 3, "nazov": "mesačný"}`` or, nested,
    ``{"id": {"id": "MZ14"}, "nazov": "D5.M"}``; prefer the name, fall back to the id.
    """
    if isinstance(obj, dict):
        return _label(obj.get("nazov")) or _label(obj.get("id"))
    return None if obj is None else str(obj)


_name = _label  # kept for brevity below



def active_contracts(vztahy: list[dict] | None) -> dict[str, dict]:
    """Map contract-account number -> its newest non-terminated contract with a delivery point."""
    out: dict[str, dict] = {}
    for v in vztahy or []:
        zu = str(v.get("zmluvnyUcetCislo") or "")
        om = v.get("odberneMiestoCislo")
        if not zu or not om:
            continue
        if (v.get("stav") or {}).get("id") == STAV_UKONCENY:
            continue
        cur = out.get(zu)
        if cur is None or (v.get("ucinnyOd") or "") > (cur.get("ucinnyOd") or ""):
            out[zu] = v
    return out


def pick_schedule(rozpisy: list[dict] | None, zu: str, today: date) -> dict | None:
    """Pick the advance-payment schedule covering today (else the newest one) for an account."""
    cands = [r for r in rozpisy or [] if str(r.get("zmluvnyUcetCislo")) == zu]
    current = [
        r
        for r in cands
        if (_d(r.get("obdobieOd")) or date.min) <= today <= (_d(r.get("obdobieDo")) or date.max)
    ]
    pool = current or cands
    return max(pool, key=lambda r: r.get("obdobieOd") or "", default=None)


def _fact(fakty: list[dict] | None, fact_id: str) -> str | None:
    """Latest value of an open-ended 'fakt' (fact) of a delivery point."""
    rows = [x for x in fakty or [] if (x.get("nazov") or {}).get("id") == fact_id]
    if not rows:
        return None
    open_ended = [x for x in rows if not x.get("platnostDo")]
    row = max(open_ended or rows, key=lambda x: x.get("platnostOd") or "")
    value = row.get("hodnota") or {}
    return value.get("nazov") or value.get("id")


def _month_after(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)



# --------------------------------------------------------------------- history
_KIND_KEY = {"advance": "advances", "settlement": "settlements", "other": "other", "refund": "refunds"}


def _pay_date(invoice: dict) -> date | None:
    """When an item was settled: its latest payment, else its due/issue date."""
    paid = [_d(p.get("platbaDatum")) for p in invoice.get("platby") or []]
    paid = [d for d in paid if d]
    if paid:
        return max(paid)
    return _d(invoice.get("splatnostDatum")) or _d(invoice.get("dokladDatum"))


def settled_events(invoices: list[dict]) -> list[dict]:
    """Money that actually moved: one event per settled (or part-settled) portal item.

    ``suma`` > 0 is something you pay, < 0 something you get back (refund / credit).
    The part still open (``sumaOtvorena``) is not counted.
    """
    out: list[dict] = []
    for f in invoices:
        suma = _f(f.get("suma"))
        if suma is None:
            continue
        amount = abs(suma) - abs(_f(f.get("sumaOtvorena")) or 0.0)
        when = _pay_date(f)
        if amount < 0.005 or when is None:
            continue
        types = {t.get("id") for t in f.get("pohladavkaTypy") or []}
        if suma < 0:
            kind = "refund"
        elif 1 in types:
            kind = "advance"
        elif TYP_SETTLEMENT in types:
            kind = "settlement"
        else:
            kind = "other"
        out.append({"date": when, "kind": kind, "amount": round(amount, 2)})
    return sorted(out, key=lambda e: e["date"])


def _summary(parts: dict[str, float]) -> dict[str, float]:
    paid = parts["advances"] + parts["settlements"] + parts["other"]
    return {
        **{k: round(v, 2) for k, v in parts.items()},
        "paid": round(paid, 2),
        "net": round(paid - parts["refunds"], 2),
    }


def cumulative(points: list[tuple[date, float]]) -> list[tuple[date, float, float]]:
    """(date, amount) points -> (date, amount that day, running total), one row per day."""
    per_day: dict[date, float] = {}
    for d, amount in points:
        per_day[d] = per_day.get(d, 0.0) + amount
    total = 0.0
    rows = []
    for d in sorted(per_day):
        total += per_day[d]
        rows.append((d, round(per_day[d], 2), round(total, 2)))
    return rows


def build_history(invoices: list[dict], spotreba: list[dict] | None, today: date) -> dict[str, Any]:
    """Payment and consumption history of one account (all values in EUR / kWh)."""
    events = settled_events(invoices)
    years: dict[int, dict[str, float]] = {}
    total = {"advances": 0.0, "settlements": 0.0, "other": 0.0, "refunds": 0.0}
    series: dict[str, list[tuple[date, float]]] = {
        "advances_paid": [],
        "settlements_paid": [],
        "other_paid": [],
        "refunds_received": [],
        "net_paid": [],
    }
    for e in events:
        key = _KIND_KEY[e["kind"]]
        bucket = years.setdefault(
            e["date"].year, {"advances": 0.0, "settlements": 0.0, "other": 0.0, "refunds": 0.0}
        )
        bucket[key] += e["amount"]
        total[key] += e["amount"]
        name = {"advances": "advances_paid", "settlements": "settlements_paid",
                "other": "other_paid", "refunds": "refunds_received"}[key]
        series[name].append((e["date"], e["amount"]))
        series["net_paid"].append((e["date"], -e["amount"] if key == "refunds" else e["amount"]))

    empty = {"advances": 0.0, "settlements": 0.0, "other": 0.0, "refunds": 0.0}
    consumption = sorted(
        (d, _f(x["spotrebaCelkom"]))
        for x in spotreba or []
        if (d := _d(x.get("datum"))) and _f(x.get("spotrebaCelkom")) is not None
    )
    return {
        "since": events[0]["date"] if events else None,
        "totals": _summary(total),
        "this_year": _summary(years.get(today.year, empty)),
        "yearly": [{"year": y, **_summary(v)} for y, v in sorted(years.items())],
        "series": series,
        "consumption": consumption,
    }


def build_account(
    zu: str,
    contract: dict,
    zucet: dict | None,
    rozpis: dict | None,
    faktury: list[dict] | None,
    spotreba: list[dict] | None,
    om_detail: dict | None,
    today: date,
) -> dict[str, Any]:
    """Compute every per-account value used by the sensors."""
    zucet = zucet or {}
    own = [f for f in faktury or [] if str(f.get("zuCislo")) == zu]

    # --- next payment -------------------------------------------------------
    open_inv = [f for f in own if (_f(f.get("sumaOtvorena")) or 0) > 0 and f.get("splatnostDatum")]
    open_inv.sort(key=lambda f: f["splatnostDatum"])

    unissued: list[dict] = []
    if rozpis:
        cislo = str(rozpis.get("cislo"))
        unissued = sorted(
            (p for p in rozpis.get("polozky") or [] if str(p.get("dokladDokumentCislo")) == cislo),
            key=lambda p: p.get("generovaneDatum") or "",
        )
    upcoming = [p for p in unissued if (_d(p.get("splatnostDatum")) or date.min) >= today]

    next_date = next_amount = next_source = None
    if open_inv:
        next_date = _d(open_inv[0]["splatnostDatum"])
        next_amount = _f(open_inv[0].get("sumaOtvorena"))
        next_source = "invoice"
    elif upcoming:
        next_date = _d(upcoming[0].get("splatnostDatum"))
        next_amount = _f(upcoming[0].get("suma"))
        next_source = "schedule"
    next_invoice = _d(upcoming[0].get("generovaneDatum")) if upcoming else None

    # --- settlements and payments -------------------------------------------
    settlements = [
        f for f in own if any(t.get("id") == TYP_SETTLEMENT for t in f.get("pohladavkaTypy") or [])
    ]
    settlements.sort(key=lambda f: f.get("dokladDatum") or "")
    last_settlement = None
    if settlements:
        s = settlements[-1]
        period = (s.get("vyuctovacieObdobia") or [{}])[0]
        paid = [
            p.get("platbaDatum")
            for p in s.get("platby") or []
            if (p.get("platbaTyp") or {}).get("id") == PAYMENT_RECEIVED
        ]
        last_settlement = {
            "date": _d(s.get("dokladDatum")),
            "due": _d(s.get("splatnostDatum")),
            "amount": _f(s.get("suma")),
            "open": _f(s.get("sumaOtvorena")),
            "paid": _d(max(paid)) if paid else None,
            "period_from": _d(period.get("vyuctovacieObdobieOd")),
            "period_to": _d(period.get("vyuctovacieObdobieDo")),
            "invoice": s.get("fakturaCislo"),
        }

    pay_dates = [
        p.get("platbaDatum")
        for f in own
        for p in f.get("platby") or []
        if (p.get("platbaTyp") or {}).get("id") == PAYMENT_RECEIVED and p.get("platbaDatum")
    ]
    last_payment = _d(max(pay_dates)) if pay_dates else None

    # --- schedule / contract -------------------------------------------------
    period_to = _d((rozpis or {}).get("obdobieDo"))
    next_settlement = _month_after(period_to) if period_to else None
    product = (contract.get("produkty") or [{}])[0]
    fakty = (om_detail or {}).get("fakty")

    series = [x for x in spotreba or [] if _f(x.get("spotrebaCelkom")) is not None]
    latest = series[-1] if series else None
    last12 = [_f(x["spotrebaCelkom"]) for x in series[-12:]]

    commodity = str(contract.get("komoditaTyp") or zucet.get("komoditaTyp") or "")
    om_detail = om_detail or {}
    due_day = zucet.get("zalohyDenSplatnostiFo")
    if not isinstance(due_day, int):  # "zalohyDenSplatnosti" is a code object ("no due date chosen")
        due_day = zucet.get("zalohyDenSplatnosti") if isinstance(zucet.get("zalohyDenSplatnosti"), int) else None
    return {
        "zu": zu,
        "commodity": commodity,
        "device_name": f"ZSE {commodity.capitalize()} {zu}".strip(),
        "next_payment_date": next_date,
        "next_payment_amount": next_amount,
        "next_payment_source": next_source,
        "next_invoice_date": next_invoice,
        "open_invoices": len(open_inv),
        "advance_amount": _f((rozpis or {}).get("zalohySuma") or contract.get("zalohySuma")),
        "advance_frequency": _name((rozpis or {}).get("zalohyCyklus")) or _name(contract.get("zalohyCyklus")),
        "advance_due_day": due_day,
        "payment_method": _name(zucet.get("doslePlatbySposob")),
        "e_invoice": bool(zucet.get("eFakturaEmaily")) if "eFakturaEmaily" in zucet else None,
        "settlement_period_from": _d((rozpis or {}).get("obdobieOd")),
        "settlement_period_to": period_to,
        "next_settlement": next_settlement,
        "last_settlement": last_settlement,
        "last_payment_date": last_payment,
        "tariff": product.get("nazov") or contract.get("produkt"),
        "product_code": product.get("kod") or contract.get("produkt"),
        "distribution_tariff": _label(contract.get("distribucnaTarifa")),
        "tariffication": _label(contract.get("tarifikacia")),
        "settlement_periodicity": _label(contract.get("zuctovaniePeriodicita")),
        "contract_valid_from": _d(contract.get("ucinnyOd")),
        "smart_meter": contract.get("smart"),
        "distributor": _label(om_detail.get("prevadzkovatelSiete")),
        "phases": _label(om_detail.get("fazyPocet")) or _fact(fakty, "O1_F_PF001"),
        "circuit_breaker_a": om_detail.get("hlavnyIsticHodnota") or _fact(fakty, "O1_M_IST01"),
        "hdo_code": om_detail.get("hdoKod") or _fact(fakty, "O1_T_HDN01"),
        "measurement_type": _label(om_detail.get("typMerania")) or _fact(fakty, "O1_T_TYM01"),
        "consumption_latest_month": _f(latest.get("spotrebaCelkom")) if latest else None,
        "consumption_latest_month_date": _d(latest.get("datum")) if latest else None,
        "consumption_monthly_average": round(mean(last12), 1) if last12 else None,
        "history": build_history(own, spotreba, today),
    }


def build(raw: dict[str, Any], today: date) -> dict[str, Any]:
    """Compute all values from the raw responses collected by api.async_fetch_raw."""
    zucty = {str(z.get("cislo")): z for z in raw.get("zucty") or []}
    accounts: dict[str, dict] = {}
    for zu, contract in active_contracts(raw.get("vztahy")).items():
        om = str(contract["odberneMiestoCislo"])
        accounts[zu] = build_account(
            zu,
            contract,
            zucty.get(zu),
            pick_schedule(raw.get("rozpisy"), zu, today),
            raw.get("faktury"),
            (raw.get("spotreba") or {}).get(zu),
            (raw.get("om_detail") or {}).get(om),
            today,
        )
    z = raw.get("zostatok") or {}
    return {
        "partner": {
            "to_pay": _f(z.get("sumaNedoplatky")),
            "overdue": _f(z.get("sumaNedoplatkyPoSplatnosti")),
            "overpayment": _f(z.get("sumaPreplatky")),
        },
        "accounts": accounts,
    }
