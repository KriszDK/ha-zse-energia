"""Names of the long-term statistics (stat_ids.py)."""
from __future__ import annotations

import importlib.util
import pathlib
import unittest

_SPEC = importlib.util.spec_from_file_location(
    "zse_stat_ids",
    pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "zse_energia" / "stat_ids.py",
)
ids = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ids)  # type: ignore[union-attr]

KEYS = ["advances_paid", "net_paid", "consumption"]


class StatIdTests(unittest.TestCase):
    def test_id_is_made_of_series_and_kind(self) -> None:
        self.assertEqual(ids.object_id("net_paid", "electricity", "6300000001", False), "net_paid_electricity")
        self.assertEqual(ids.object_id("net_paid", "gas", "6300000002", False), "net_paid_gas")

    def test_account_number_is_added_on_request(self) -> None:
        self.assertEqual(
            ids.object_id("net_paid", "electricity", "6300000001", True), "net_paid_electricity_6300000001"
        )

    def test_unknown_kinds_stay_safe(self) -> None:
        self.assertEqual(ids.kind_slug("Voda / Water!"), "voda_water")
        self.assertEqual(ids.kind_slug(""), "other")

    def test_legacy_id(self) -> None:
        self.assertEqual(ids.legacy_object_id("net_paid", "6300000001"), "net_paid_6300000001")

    def test_one_account_per_kind_needs_no_number(self) -> None:
        accounts = {"6300000001": {"kind": "electricity"}, "6300000002": {"kind": "gas"}}
        self.assertEqual(ids.numbers_needed(accounts), set())

    def test_several_accounts_of_one_kind_need_the_number(self) -> None:
        accounts = {
            "6300000001": {"kind": "electricity"},
            "6300000003": {"kind": "electricity"},
            "6300000002": {"kind": "gas"},
        }
        self.assertEqual(ids.numbers_needed(accounts), {"6300000001", "6300000003"})

    def test_obsolete_ids_cover_the_legacy_and_the_other_scheme(self) -> None:
        plain = ids.obsolete_object_ids(KEYS, "gas", "6300000002", False)
        self.assertIn("net_paid_6300000002", plain)  # before 0.5.0
        self.assertIn("net_paid_gas_6300000002", plain)  # option was on before
        self.assertNotIn("net_paid_gas", plain)

    def test_the_plain_id_of_another_account_is_never_removed(self) -> None:
        numbered = ids.obsolete_object_ids(KEYS, "electricity", "6300000001", True)
        self.assertEqual(numbered, sorted(f"{k}_6300000001" for k in KEYS))
        self.assertNotIn("net_paid_electricity", numbered)


if __name__ == "__main__":
    unittest.main()
