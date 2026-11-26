"""Offline tests for parser.py using synthetic data shaped like the real portal responses.

Run:  python -m unittest discover -s tests -v   (from the repository root)
"""
from __future__ import annotations

import importlib.util
import pathlib
import unittest
from datetime import date

_SPEC = importlib.util.spec_from_file_location(
    "zse_parser",
    pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "zse_energia" / "parser.py",
)
parser = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(parser)  # type: ignore[union-attr]

ZU, OM, ROZPIS = "6300000001", "4100000001", "160000000001"


def _item(gen: str, due: str, doc: object) -> dict:
    return {
        "generovaneDatum": gen,
        "suma": 49.0,
        "splatnostDatum": due,
        "vyrovnanieStatus": {"id": 1, "nazov": "otvorená položka"},
        "dokladDokumentCislo": doc,
    }


def raw(faktury) -> dict:
    return {
        "zucty": [
            {
                "cislo": ZU,
                "komoditaTyp": "ELEKTRINA",
                "zalohyDenSplatnosti": {"id": 1, "nazov": "bez výberu splatnosti"},
                "zalohyDenSplatnostiFo": 15,
                "doslePlatbySposob": {"id": 2, "nazov": "inkasný príkaz"},
                "eFakturaEmaily": [{"email": "x@example.invalid", "pdf": True}],
            }
        ],
        "vztahy": [
            {  # ended contract of the same account must lose against the active one
                "cislo": "0100000001",
                "zmluvnyUcetCislo": ZU,
                "odberneMiestoCislo": OM,
                "stav": {"id": 4, "nazov": "ukončený"},
                "ucinnyOd": "2015-02-20T00:00:00",
                "produkty": [{"kod": "OLD", "nazov": "Old"}],
            },
            {
                "cislo": "0100000002",
                "zmluvnyUcetCislo": ZU,
                "odberneMiestoCislo": OM,
                "komoditaTyp": "ELEKTRINA",
                "stav": {"id": 3, "nazov": "účinný"},
                "ucinnyOd": "2020-01-01T00:00:00",
                "produkty": [{"kod": "D11.R", "nazov": "DD5,DD6 - DomovVykurovanie (ročný)"}],
                "distribucnaTarifa": {"id": {"id": "MZ14"}, "nazov": "D5.M"},
                "tarifikacia": {"id": "2P", "nazov": "2P"},
                "zuctovaniePeriodicita": {"id": "R", "nazov": "ročná"},
                "smart": True,
            },
            {"cislo": "0100000003", "komoditaTyp": "NEZNAMA", "produkty": [{"kod": "KOL02-B"}]},
        ],
        "rozpisy": [
            {
                "cislo": ROZPIS,
                "zmluvnyUcetCislo": ZU,
                "obdobieOd": "2026-11-01",
                "obdobieDo": "2027-10-31",
                "zalohySuma": 49.0,
                "zalohyCyklus": {"id": 3, "nazov": "mesačný"},
                "polozky": [
                    _item("2026-11-24", "2026-12-15", 7600000001),
                    _item("2026-12-24", "2027-01-15", int(ROZPIS)),
                    _item("2027-01-24", "2027-02-15", int(ROZPIS)),
                ],
            }
        ],
        "zostatok": {
            "sumaOtvorena": 49.0,
            "sumaNedoplatky": 49.0,
            "sumaPoSplatnosti": 0,
            "sumaNedoplatkyPoSplatnosti": 0,
            "sumaPreplatky": 0,
        },
        "faktury": faktury,
        "om_detail": {
            OM: {
                "identifikator": "24ZZ0000000000X",
                "msCislo": "3100000001",
                "fazyPocet": {"id": 3, "nazov": "3"},
                "hlavnyIsticHodnota": "25.00",
                "hdoKod": "659346",
                "prevadzkovatelSiete": {"id": "ED-ZSE", "nazov": "ZSE Distribúcia"},
                "fakty": [
                    {"nazov": {"id": "O1_M_IST01"}, "platnostOd": "2012-01-01", "hodnota": {"id": "25.00"}},
                    {
                        "nazov": {"id": "O1_T_HDN01"},
                        "platnostOd": "2010-10-16",
                        "platnostDo": "2021-10-14",
                        "hodnota": {"id": "159146"},
                    },
                    {"nazov": {"id": "O1_T_HDN01"}, "platnostOd": "2021-10-15", "hodnota": {"id": "659346"}},
                ],
            }
        },
        "spotreba": {
            ZU: [{"datum": f"2026-{m:02d}-28", "spotrebaCelkom": float(m * 10)} for m in range(1, 11)]
        },
    }


FAKTURY = [
    {
        "id": "7600000001.2026-12-15",
        "fakturaCislo": "7600000001",
        "pohladavkaTypy": [{"id": 1, "nazov": "Záloha komodita"}],
        "zuCislo": ZU,
        "dokladDatum": "2026-11-22",
        "splatnostDatum": "2026-12-15",
        "suma": 49.0,
        "sumaOtvorena": 49.0,
        "platby": [],
    },
    {
        "id": "7100000002.2026-11-19",
        "fakturaCislo": "7100000002",
        "pohladavkaTypy": [{"id": 3, "nazov": "Faktúra vyúčtovacia"}],
        "zuCislo": ZU,
        "dokladDatum": "2026-11-05",
        "splatnostDatum": "2026-11-19",
        "suma": -119.44,
        "sumaOtvorena": 0,
        "platby": [{"id": "2013", "platbaDatum": "2026-11-18", "platbaTyp": {"id": 1}}],
        "vyuctovacieObdobia": [
            {"vyuctovacieObdobieOd": "2025-11-01", "vyuctovacieObdobieDo": "2026-10-31"}
        ],
    },
    {
        "id": "7600000003.2026-10-15",
        "fakturaCislo": "7600000003",
        "pohladavkaTypy": [{"id": 1, "nazov": "Záloha komodita"}],
        "zuCislo": ZU,
        "dokladDatum": "2026-09-21",
        "splatnostDatum": "2026-10-15",
        "suma": 61.0,
        "sumaOtvorena": 0,
        "platby": [{"id": "2000", "platbaDatum": "2026-10-15", "platbaTyp": {"id": 1}}],
    },
]


class ParserTests(unittest.TestCase):
    def test_open_invoice_is_next_payment(self) -> None:
        acc = parser.build(raw(FAKTURY), date(2026, 11, 24))["accounts"][ZU]
        self.assertEqual(acc["next_payment_date"], date(2026, 12, 15))
        self.assertEqual(acc["next_payment_amount"], 49.0)
        self.assertEqual(acc["next_payment_source"], "invoice")
        self.assertEqual(acc["open_invoices"], 1)
        # next advance invoice = first schedule item that is not yet issued
        self.assertEqual(acc["next_invoice_date"], date(2026, 12, 24))

    def test_schedule_fallback_when_all_paid(self) -> None:
        paid = [dict(f, sumaOtvorena=0) for f in FAKTURY]
        acc = parser.build(raw(paid), date(2026, 12, 20))["accounts"][ZU]
        self.assertEqual(acc["next_payment_source"], "schedule")
        self.assertEqual(acc["next_payment_date"], date(2027, 1, 15))
        self.assertEqual(acc["open_invoices"], 0)

    def test_no_invoice_data(self) -> None:
        acc = parser.build(raw(None), date(2026, 11, 24))["accounts"][ZU]
        self.assertEqual(acc["next_payment_source"], "schedule")
        self.assertEqual(acc["next_payment_date"], date(2027, 1, 15))
        self.assertIsNone(acc["last_settlement"])
        self.assertIsNone(acc["last_payment_date"])

    def test_settlement_and_payments(self) -> None:
        acc = parser.build(raw(FAKTURY), date(2026, 11, 24))["accounts"][ZU]
        s = acc["last_settlement"]
        self.assertEqual(s["amount"], -119.44)
        self.assertEqual(s["date"], date(2026, 11, 5))
        self.assertEqual(s["paid"], date(2026, 11, 18))
        self.assertEqual(s["period_from"], date(2025, 11, 1))
        self.assertEqual(s["period_to"], date(2026, 10, 31))
        self.assertEqual(acc["last_payment_date"], date(2026, 11, 18))
        self.assertEqual(acc["next_settlement"], date(2027, 11, 1))

    def test_contract_and_facts(self) -> None:
        acc = parser.build(raw(FAKTURY), date(2026, 11, 24))["accounts"][ZU]
        self.assertEqual(acc["tariff"], "DD5,DD6 - DomovVykurovanie (ročný)")
        self.assertEqual(acc["product_code"], "D11.R")
        self.assertEqual(acc["payment_method"], "inkasný príkaz")
        self.assertEqual(acc["advance_frequency"], "mesačný")
        self.assertEqual(acc["advance_due_day"], 15)  # from ...Fo, not the "no due date chosen" code
        self.assertEqual(acc["distribution_tariff"], "D5.M")  # nested code object flattened
        self.assertEqual(acc["tariffication"], "2P")
        self.assertEqual(acc["settlement_periodicity"], "ročná")
        self.assertEqual(acc["contract_valid_from"], date(2020, 1, 1))
        self.assertEqual(acc["phases"], "3")
        self.assertEqual(acc["circuit_breaker_a"], "25.00")
        self.assertEqual(acc["hdo_code"], "659346")
        self.assertEqual(acc["distributor"], "ZSE Distribúcia")
        self.assertNotIn("eic", acc)  # identifiers are never exposed
        self.assertNotIn("delivery_point_number", acc)
        self.assertIs(acc["e_invoice"], True)
        self.assertNotIn("refund_account", acc)  # bank account numbers are never exposed
        self.assertNotIn("debit_account", acc)
        self.assertEqual(acc["device_name"], f"ZSE Elektrina {ZU}")

    def test_facts_fallback_without_top_level_fields(self) -> None:
        r = raw(FAKTURY)
        for k in ("fazyPocet", "hlavnyIsticHodnota", "hdoKod"):
            r["om_detail"][OM].pop(k)
        acc = parser.build(r, date(2026, 11, 24))["accounts"][ZU]
        self.assertEqual(acc["circuit_breaker_a"], "25.00")  # from fakty
        self.assertEqual(acc["hdo_code"], "659346")  # open-ended fakt wins over the expired one

    def test_label_variants(self) -> None:
        self.assertEqual(parser._label({"id": {"id": "MZ14"}}), "MZ14")
        self.assertEqual(parser._label({"id": 3, "nazov": "mesačný"}), "mesačný")
        self.assertIsNone(parser._label(None))

    def test_only_active_accounts(self) -> None:
        data = parser.build(raw(FAKTURY), date(2026, 11, 24))
        self.assertEqual(list(data["accounts"]), [ZU])

    def test_balance_and_consumption(self) -> None:
        data = parser.build(raw(FAKTURY), date(2026, 11, 24))
        self.assertEqual(data["partner"], {"to_pay": 49.0, "overdue": 0.0, "overpayment": 0.0})
        acc = data["accounts"][ZU]
        self.assertEqual(acc["consumption_latest_month"], 100.0)
        self.assertEqual(acc["consumption_monthly_average"], 55.0)  # mean(10..100)

    def test_month_after_december(self) -> None:
        self.assertEqual(parser._month_after(date(2026, 12, 31)), date(2027, 1, 1))
        self.assertEqual(parser._month_after(date(2027, 10, 31)), date(2027, 11, 1))

    def test_empty_input(self) -> None:
        data = parser.build({}, date(2026, 11, 24))
        self.assertEqual(data["accounts"], {})


def inv(num, types, suma, open_, pay=None, due="2024-01-15", doc="2024-01-01"):
    return {
        "id": num,
        "fakturaCislo": num,
        "pohladavkaTypy": [{"id": t} for t in types],
        "zuCislo": ZU,
        "dokladDatum": doc,
        "splatnostDatum": due,
        "suma": suma,
        "sumaOtvorena": open_,
        "platby": [{"platbaDatum": pay, "platbaTyp": {"id": 1}}] if pay else [],
    }


HIST = [
    inv("a1", [1], 50.0, 0, pay="2024-01-15"),
    inv("a2", [1, 9], 60.0, 0, pay="2024-02-15"),  # advance + service fee in one item
    inv("s1", [3], 30.0, 0, pay="2024-11-20"),  # settlement surcharge
    inv("r1", [3], -100.0, 0, pay="2025-11-18"),  # settlement refund
    inv("o1", [7], 20.0, 0, pay="2016-12-07"),  # other (e.g. corrective invoice)
    inv("u1", [1], 49.0, 49.0, due="2026-12-15"),  # not paid yet: ignored
    inv("p1", [1], 50.0, 20.0, pay="2026-01-15"),  # partly paid: only 30 counts
    inv("n1", [1], 40.0, 0),  # settled but no payment record: due date is used
]


class HistoryTests(unittest.TestCase):
    TODAY = date(2026, 11, 24)

    def history(self, spotreba=None) -> dict:
        return parser.build_history(HIST, spotreba, self.TODAY)

    def test_unpaid_items_are_ignored_and_partial_counted(self) -> None:
        events = parser.settled_events(HIST)
        self.assertEqual(len(events), 7)
        self.assertNotIn("u1", [e.get("id") for e in events])
        partly = [e for e in events if e["date"] == date(2026, 1, 15)]
        self.assertEqual(partly[0]["amount"], 30.0)

    def test_totals(self) -> None:
        t = self.history()["totals"]
        self.assertEqual(t["advances"], 180.0)  # 50 + 60 + 30 + 40
        self.assertEqual(t["settlements"], 30.0)
        self.assertEqual(t["other"], 20.0)
        self.assertEqual(t["refunds"], 100.0)
        self.assertEqual(t["paid"], 230.0)
        self.assertEqual(t["net"], 130.0)

    def test_yearly_buckets(self) -> None:
        by_year = {y["year"]: y for y in self.history()["yearly"]}
        self.assertEqual(sorted(by_year), [2016, 2024, 2025, 2026])
        self.assertEqual(by_year[2016]["other"], 20.0)
        self.assertEqual(by_year[2024]["advances"], 150.0)  # a1 + a2 + n1 (fallback date)
        self.assertEqual(by_year[2024]["settlements"], 30.0)
        self.assertEqual(by_year[2025]["refunds"], 100.0)
        self.assertEqual(by_year[2025]["net"], -100.0)
        self.assertEqual(by_year[2026]["advances"], 30.0)

    def test_this_year_and_since(self) -> None:
        h = self.history()
        self.assertEqual(h["this_year"]["paid"], 30.0)
        self.assertEqual(h["since"], date(2016, 12, 7))

    def test_series_net_is_signed(self) -> None:
        h = self.history()
        self.assertEqual(round(sum(v for _, v in h["series"]["net_paid"]), 2), 130.0)
        self.assertEqual(round(sum(v for _, v in h["series"]["refunds_received"]), 2), 100.0)

    def test_cumulative(self) -> None:
        d1, d2 = date(2024, 1, 1), date(2024, 2, 1)
        rows = parser.cumulative([(d2, -3.0), (d1, 10.0), (d1, 5.0)])
        self.assertEqual(rows, [(d1, 15.0, 15.0), (d2, -3.0, 12.0)])
        self.assertEqual(parser.cumulative([]), [])

    def test_consumption_series(self) -> None:
        h = self.history([{"datum": "2026-02-28", "spotrebaCelkom": 5}, {"datum": "2026-01-31", "spotrebaCelkom": 7}])
        self.assertEqual(h["consumption"], [(date(2026, 1, 31), 7.0), (date(2026, 2, 28), 5.0)])

    def test_no_data(self) -> None:
        h = parser.build_history([], None, self.TODAY)
        self.assertIsNone(h["since"])
        self.assertEqual(h["totals"]["net"], 0.0)
        self.assertEqual(h["yearly"], [])

    def test_history_is_part_of_account(self) -> None:
        r = raw(FAKTURY)
        acc = parser.build(r, date(2026, 11, 24))["accounts"][ZU]
        self.assertIn("history", acc)
        # FAKTURY: 61 € advance paid 2026-10-15, settlement -119.44 refunded 2026-11-18
        self.assertEqual(acc["history"]["totals"]["refunds"], 119.44)
        self.assertEqual(acc["history"]["totals"]["advances"], 61.0)


if __name__ == "__main__":
    unittest.main()
