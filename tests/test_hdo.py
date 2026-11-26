"""Low/high tariff (HDO) logic: parsing the ZSDIS page data, windows, status."""
import importlib.util
import json
import pathlib
import sys
import unittest
from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # pragma: no cover - no tz database on this machine
    TZ = None

PKG = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "zse_energia"
spec = importlib.util.spec_from_file_location("hdo", PKG / "hdo.py")
hdo = importlib.util.module_from_spec(spec)
sys.modules["hdo"] = hdo
spec.loader.exec_module(hdo)

SNAPSHOT = json.loads((PKG / "hdo_programs.json").read_text(encoding="utf-8"))["programs"]

JS = """
var household_rates = [{
    code: 659,
    intervals: [{
        telegram: '',
        t_type: 'nt',
        t_from: '00:15',
        t_to: '06:30',
        weekday: true,
        weekend: true,
        meaning: 'Priamovýhrevné vykurovanie, nabíjacia stanica',
        for_rate: 'D3 Aktiv (DD5*)',
        tarification: '2P'
    }]
}];
var business_rates = [{ code: 101, intervals: [] }];
"""


@unittest.skipIf(TZ is None, "no timezone database")
class HdoTests(unittest.TestCase):
    def test_split_code(self) -> None:
        self.assertEqual(hdo.split_code("659346"), [659, 346])
        self.assertEqual(hdo.split_code(659), [659])
        self.assertEqual(hdo.split_code("65"), [])
        self.assertEqual(hdo.split_code(None), [])

    def test_parse_js_literal(self) -> None:
        # a page with only two programs is rejected as suspicious
        with self.assertRaises(hdo.HdoParseError):
            hdo.extract_rates(JS)
        value, _ = hdo._parse_value("[{a: 'x\\'y', b: [1, 2.5, true, null], c: \"q\"},]", 0)
        self.assertEqual(value, [{"a": "x'y", "b": [1, 2.5, True, None], "c": "q"}])
        with self.assertRaises(hdo.HdoParseError):
            hdo.extract_rates("nothing here")

    def test_absurd_nesting_is_a_parse_error(self) -> None:
        deep = "var household_rates = " + "[" * 100_000 + "]" * 100_000 + ";"
        with self.assertRaises(hdo.HdoParseError):
            hdo.extract_rates(deep)

    def test_snapshot_has_all_programs(self) -> None:
        codes = {p["code"] for p in SNAPSHOT}
        self.assertEqual(len(SNAPSHOT), 44)
        self.assertTrue({659, 346, 359, 101} <= codes)

    def test_program_659346_windows(self) -> None:
        iv = hdo.tariff_intervals(SNAPSHOT, "659346")  # 346 is supplementary: no tarification, left out
        self.assertEqual(len(iv), 5)
        snap = hdo.snapshot(iv, datetime(2026, 11, 24, 12, 0, tzinfo=TZ), TZ)
        self.assertEqual(
            snap.high_today, ("00:00-00:15", "06:30-07:30", "08:45-09:15", "10:15-11:15", "21:30-22:00", "23:15-24:00")
        )
        self.assertAlmostEqual(snap.high_hours_today, 4.0)
        self.assertEqual(snap.high_tomorrow, snap.high_today)  # same program all week
        self.assertTrue(snap.low)
        self.assertEqual(snap.changes_at, datetime(2026, 11, 24, 21, 30, tzinfo=TZ))
        self.assertEqual(snap.next_low_start, datetime(2026, 11, 24, 22, 0, tzinfo=TZ))

    def test_high_tariff_now(self) -> None:
        iv = hdo.tariff_intervals(SNAPSHOT, "659346")
        snap = hdo.snapshot(iv, datetime(2026, 11, 24, 6, 40, tzinfo=TZ), TZ)
        self.assertFalse(snap.low)
        self.assertEqual(snap.changes_at, datetime(2026, 11, 24, 7, 30, tzinfo=TZ))
        self.assertEqual(snap.refresh_at, snap.changes_at)

    def test_window_over_midnight_and_weekend(self) -> None:
        iv = [
            {"t_type": "nt", "tarification": "2T", "t_from": "22:00", "t_to": "6:00", "weekday": True, "weekend": False},
            {"t_type": "nt", "tarification": "2T", "t_from": "0:00", "t_to": "24:00", "weekday": False, "weekend": True},
        ]
        # Friday 23:00 is low; it stays low over the whole weekend until Monday 06:00
        fri = datetime(2026, 11, 27, 23, 0, tzinfo=TZ)
        snap = hdo.snapshot(iv, fri, TZ)
        self.assertTrue(snap.low)
        self.assertEqual(snap.changes_at, datetime(2026, 11, 30, 6, 0, tzinfo=TZ))
        # Tuesday noon is high; low starts at 22:00
        tue = hdo.snapshot(iv, datetime(2026, 12, 1, 12, 0, tzinfo=TZ), TZ)
        self.assertFalse(tue.low)
        self.assertEqual(tue.changes_at, datetime(2026, 12, 1, 22, 0, tzinfo=TZ))
        # the refresh never lies behind midnight
        self.assertLessEqual(snap.refresh_at, datetime(2026, 11, 28, 0, 0, tzinfo=TZ))

    def test_permanent_winter_time_shifts_summer_windows_only(self) -> None:
        iv = hdo.tariff_intervals(SNAPSHOT, "659346")
        summer = hdo.low_windows(iv, date(2026, 7, 1), TZ, winter_time=True)
        self.assertEqual(summer[0].start, datetime(2026, 7, 1, 1, 15, tzinfo=TZ))  # 00:15 + 1 h
        winter = hdo.low_windows(iv, date(2026, 12, 1), TZ, winter_time=True)
        self.assertEqual(winter[0].start, datetime(2026, 12, 1, 0, 15, tzinfo=TZ))  # unchanged
        plain = hdo.low_windows(iv, date(2026, 7, 1), TZ, winter_time=False)
        self.assertEqual(plain[0].start, datetime(2026, 7, 1, 0, 15, tzinfo=TZ))

    def test_timeline_alternates(self) -> None:
        iv = hdo.tariff_intervals(SNAPSHOT, "659346")
        start = datetime(2026, 11, 24, 0, 0, tzinfo=TZ)
        low = hdo.windows_between(iv, start, start + timedelta(days=1), TZ)
        segments = hdo.timeline(low, start, start + timedelta(days=1))
        kinds = [is_low for is_low, _ in segments]
        self.assertTrue(all(a != b for a, b in zip(kinds, kinds[1:])))
        # contiguous
        for (_, a), (_, b) in zip(segments, segments[1:]):
            self.assertEqual(a.end, b.start)

    def test_supplementary_only_code_has_no_tariff(self) -> None:
        self.assertEqual(hdo.tariff_intervals(SNAPSHOT, "346"), [])
        self.assertEqual(hdo.tariff_intervals(SNAPSHOT, ""), [])

    def test_daylight_saving_day_length(self) -> None:
        # 2026-03-29 has 23 hours: the high-tariff total is computed from real durations
        iv = [{"t_type": "nt", "tarification": "2T", "t_from": "22:00", "t_to": "6:00", "weekday": True, "weekend": True}]
        snap = hdo.snapshot(iv, datetime(2026, 3, 29, 12, 0, tzinfo=TZ), TZ)
        self.assertAlmostEqual(snap.high_hours_today, 16.0, places=1)  # 06:00-22:00; the missing hour is in the night
