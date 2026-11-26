"""Gas contracts: synthetic data shaped like the real portal responses of a gas account."""
from __future__ import annotations

import importlib.util
import pathlib
import unittest
from datetime import date

_SPEC = importlib.util.spec_from_file_location(
    "zse_parser_gas",
    pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "zse_energia" / "parser.py",
)
parser = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(parser)  # type: ignore[union-attr]

ZU, OM, ROZPIS = "6300000002", "4900000001", "160000000002"
TODAY = date(2026, 11, 25)


def fact(fact_id: str, name: str, start: str, end: str | None, value: str) -> dict:
    return {
        "omCislo": OM,
        "nazov": {"id": fact_id, "nazov": name},
        "platnostOd": start,
        "platnostDo": end,
        "hodnota": {"id": value},
    }


RAW = {
    "zucty": [
        {
            "cislo": ZU,
            "komoditaTyp": "PLYN",
            "doslePlatbySposob": {"id": 1, "nazov": "inkasný príkaz"},
            "zalohyDenSplatnostiFo": 25,
            "eFakturaEmaily": [{"email": "x@example.com", "pdf": True}],
        }
    ],
    "vztahy": [
        {  # an old, terminated contract of the same account
            "cislo": "1",
            "zmluvnyUcetCislo": ZU,
            "komoditaTyp": "PLYN",
            "stav": {"id": 4, "nazov": "ukončený"},
            "ucinnyOd": "2015-04-01T00:00:00",
            "produkty": [{"kod": "AS01-A", "nazov": "ZSE Asistuje"}],
        },
        {
            "cislo": "2",
            "zmluvnyUcetCislo": ZU,
            "odberneMiestoCislo": OM,
            "komoditaTyp": "PLYN",
            "stav": {"id": 3, "nazov": "účinný"},
            "ucinnyOd": "2015-05-01T00:00:00",
            "produkty": [{"kod": "GD02.R", "nazov": "D2 ročný"}],
            "distribucnaTarifa": "D2",
            "zuctovaniePeriodicita": "ročná",
            "spotrebaPredpokladana": 11605,
            "spotrebaPredpokladanaM3": 1086,
            "ucelPouzitiaGas": {"tuv": True, "varenie": True, "vykurovanie": True},
            "zalohyCyklus": "mesačný",
            "zalohySuma": 73,
        },
    ],
    "rozpisy": [
        {
            "cislo": ROZPIS,
            "zmluvnyUcetCislo": ZU,
            "obdobieOd": "2026-06-01",
            "obdobieDo": "2027-05-31",
            "zalohySuma": 82,
            "zalohyCyklus": {"id": 1, "nazov": "mesačný"},
            "polozky": [
                {
                    "generovaneDatum": "2026-12-10",
                    "suma": 82,
                    "splatnostDatum": "2026-12-25",
                    "dokladDokumentCislo": ROZPIS,
                }
            ],
        }
    ],
    "zostatok": {"sumaOtvorena": 82, "sumaNedoplatky": 82, "sumaPreplatky": 0, "sumaNedoplatkyPoSplatnosti": 0},
    "faktury": [
        {
            "id": "1",
            "zuCislo": ZU,
            "pohladavkaTypy": [{"id": 1, "nazov": "Záloha komodita"}],
            "dokladDatum": "2026-11-05",
            "splatnostDatum": "2026-11-25",
            "suma": 82,
            "sumaOtvorena": 82,
            "platby": [],
        },
        {
            "id": "2",
            "zuCislo": ZU,
            "pohladavkaTypy": [{"id": 3, "nazov": "Faktúra vyúčtovacia"}],
            "dokladDatum": "2026-06-09",
            "splatnostDatum": "2026-06-25",
            "suma": -153.37,
            "sumaOtvorena": 0,
            "platby": [{"platbaDatum": "2026-06-25", "platbaTyp": {"id": 1}}],
        },
    ],
    "om_detail": {
        OM: {
            "prevadzkovatelSiete": {"id": "SPP", "nazov": "SPP – distribúcia, a.s."},
            "fakty": [
                fact("G_M_DSP010", "Dodaná spotreba plynu", "2025-06-01", "2025-12-31", "5866.00"),
                fact("G_M_DSP010", "Dodaná spotreba plynu", "2026-01-01", "2026-05-31", "4157.00"),
                fact("G_N_DRT001", "Druh tar.pre vypočty/Typ OM", "2026-01-01", None, "DOM Regulovana bez AEP"),
                fact("G_N_DRT002", "Druh Tarify pre Cenniky", "2020-05-01", "2025-12-31", "GAS MOO Štandardný cenník 1"),
            ],
            "spotrebaSkutocna": [
                {"hodnota": 4157, "obdobieOd": "2026-01-01", "obdobieDo": "2026-05-31"},
                {"hodnota": 389, "jednotka": "m3", "obdobieOd": "2026-01-01", "obdobieDo": "2026-05-31"},
            ],
            "odpocty": [{"hodnota": 7891, "jednotka": "m3", "obdobieDo": "2026-05-31"}],
        }
    },
    "spotreba": {ZU: None},  # the monthly series call fails for gas
}


class GasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = parser.build(RAW, TODAY)
        self.acc = self.data["accounts"][ZU]

    def test_kind_and_device(self) -> None:
        self.assertEqual(self.acc["kind"], "gas")
        self.assertEqual(self.acc["device_name"], f"ZSE Plyn {ZU}")
        self.assertEqual(parser.kind_of("ELEKTRINA"), "electricity")
        self.assertEqual(parser.kind_of("XYZ"), "xyz")

    def test_generic_values_work_for_gas(self) -> None:
        a = self.acc
        self.assertEqual(a["tariff"], "D2 ročný")
        self.assertEqual(a["distribution_tariff"], "D2")
        self.assertEqual(a["settlement_periodicity"], "ročná")
        self.assertEqual(a["payment_method"], "inkasný príkaz")
        self.assertEqual(a["advance_amount"], 82.0)
        self.assertEqual(a["advance_due_day"], 25)
        self.assertEqual(a["next_payment_date"], date(2026, 11, 25))  # the open advance invoice
        self.assertEqual(a["next_payment_amount"], 82.0)
        self.assertEqual(a["next_settlement"], date(2027, 6, 1))
        self.assertEqual(a["last_settlement"]["amount"], -153.37)
        self.assertEqual(a["distributor"], "SPP – distribúcia, a.s.")
        self.assertIsNone(a["hdo_code"])

    def test_gas_values(self) -> None:
        a = self.acc
        self.assertEqual(a["gas_consumption_last"], 4157.0)
        self.assertEqual(a["gas_consumption_last_from"], date(2026, 1, 1))
        self.assertEqual(a["gas_consumption_last_to"], date(2026, 5, 31))
        self.assertEqual(a["gas_consumption_last_m3"], 389.0)
        self.assertEqual(a["expected_consumption_kwh"], 11605.0)
        self.assertEqual(a["expected_consumption_m3"], 1086.0)
        self.assertEqual((a["meter_reading"], a["meter_reading_unit"], a["meter_reading_date"]), (7891.0, "m3", date(2026, 5, 31)))
        self.assertEqual(a["price_list"], "DOM Regulovana bez AEP")  # the current type, not the ended price list
        self.assertEqual(a["gas_use"], ["cooking", "heating", "hot_water"])
        self.assertEqual(
            a["gas_periods"],
            [
                {"from": "2025-06-01", "to": "2025-12-31", "kwh": 5866.0},
                {"from": "2026-01-01", "to": "2026-05-31", "kwh": 4157.0},
            ],
        )

    def test_each_billing_period_is_one_point_at_its_end(self) -> None:
        periods = parser.gas_periods(RAW["om_detail"][OM]["fakty"])
        self.assertEqual([p["kwh"] for p in periods], [5866.0, 4157.0])
        self.assertEqual(parser.period_points(periods), [(date(2025, 12, 31), 5866.0), (date(2026, 5, 31), 4157.0)])

    def test_history_uses_the_gas_periods_as_consumption(self) -> None:
        consumption = self.acc["history"]["consumption"]
        self.assertEqual(consumption, [(date(2025, 12, 31), 5866.0), (date(2026, 5, 31), 4157.0)])
        self.assertEqual(self.acc["history"]["totals"]["refunds"], 153.37)

    def test_missing_gas_facts_do_not_break_anything(self) -> None:
        raw = dict(RAW, om_detail={OM: {}})
        acc = parser.build(raw, TODAY)["accounts"][ZU]
        self.assertIsNone(acc["gas_consumption_last"])
        self.assertIsNone(acc["meter_reading"])
        self.assertEqual(acc["history"]["consumption"], [])


if __name__ == "__main__":
    unittest.main()
