"""Low/high tariff (HDO) schedules of ZSDIS, the distribution company.

The public page https://www.zsdis.sk/Uvod/Online-sluzby/Casy-prepinania-nizkej-a-vysokej-tarify has no API:
the tables are JavaScript data (``household_rates`` / ``business_rates``) inside the HTML. This module
parses that data and answers "is the low tariff active now / when does it change". It has no Home Assistant
imports, so it can be tested on its own.

A meter's HDO code is one or more 3-digit programs written together, e.g. ``659346`` = programs 659 and 346.
Every program lists the time windows of the LOW tariff ("nt"); the high tariff is the rest of the day.
Windows may run over midnight (``23:45``-``5:45``) and apply to weekdays and/or weekends.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

PAGE_URL = "https://www.zsdis.sk/Uvod/Online-sluzby/Casy-prepinania-nizkej-a-vysokej-tarify"
VARIABLES = ("household_rates", "business_rates")


class HdoParseError(ValueError):
    """The page does not contain the tables in the expected form."""


# --------------------------------------------------------------------------------------------- JS literal
_WS = re.compile(r"\s+")
_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


def _skip(text: str, i: int) -> int:
    return _WS.match(text, i).end() if _WS.match(text, i) else i


def _parse_value(text: str, i: int) -> tuple[Any, int]:
    """Parse one JavaScript literal (objects with bare keys, 'single quoted' strings, true/false/null)."""
    i = _skip(text, i)
    if i >= len(text):
        raise HdoParseError("unexpected end of data")
    c = text[i]
    if c == "{":
        out: dict[str, Any] = {}
        i = _skip(text, i + 1)
        while text[i] != "}":
            if text[i] in "'\"":
                key, i = _parse_value(text, i)
            else:
                m = _IDENT.match(text, i)
                if not m:
                    raise HdoParseError(f"bad key at {i}")
                key, i = m.group(0), m.end()
            i = _skip(text, i)
            if text[i] != ":":
                raise HdoParseError(f"':' expected at {i}")
            out[key], i = _parse_value(text, i + 1)
            i = _skip(text, i)
            if text[i] == ",":
                i = _skip(text, i + 1)
        return out, i + 1
    if c == "[":
        items: list[Any] = []
        i = _skip(text, i + 1)
        while text[i] != "]":
            value, i = _parse_value(text, i)
            items.append(value)
            i = _skip(text, i)
            if text[i] == ",":
                i = _skip(text, i + 1)
        return items, i + 1
    if c in "'\"":
        end, chars = i + 1, []
        while text[end] != c:
            if text[end] == "\\":
                end += 1
            chars.append(text[end])
            end += 1
        return "".join(chars), end + 1
    m = _NUM.match(text, i)
    if m:
        number = float(m.group(0))
        return (int(number) if number.is_integer() else number), m.end()
    m = _IDENT.match(text, i)
    if m and m.group(0) in ("true", "false", "null"):
        return {"true": True, "false": False, "null": None}[m.group(0)], m.end()
    raise HdoParseError(f"unexpected token at {i}")


def extract_rates(html: str) -> list[dict[str, Any]]:
    """All programs of the page: ``[{"code": 659, "intervals": [...]}, ...]``."""
    programs: list[dict[str, Any]] = []
    for name in VARIABLES:
        m = re.search(name + r"\s*=\s*\[", html)
        if not m:
            raise HdoParseError(f"{name} not found")
        try:
            value, _ = _parse_value(html, m.end() - 1)
        except (IndexError, ValueError) as err:
            raise HdoParseError(f"{name}: {err}") from err
        programs += [p for p in value if isinstance(p, dict) and "code" in p and "intervals" in p]
    if len(programs) < 10:
        raise HdoParseError(f"only {len(programs)} programs found")
    return programs


# ------------------------------------------------------------------------------------------- selection
def split_code(hdo_code: Any) -> list[int]:
    """``"659346"`` -> ``[659, 346]``; ``"659"`` -> ``[659]``; junk -> ``[]``."""
    digits = re.sub(r"\D", "", str(hdo_code or ""))
    if not digits or len(digits) % 3:
        return []
    return [int(digits[i : i + 3]) for i in range(0, len(digits), 3)]


def tariff_intervals(programs: list[dict[str, Any]], hdo_code: Any) -> list[dict[str, Any]]:
    """The low-tariff windows that apply to a meter.

    Only windows with a tarification ("2T", "2P", "2A") switch the tariff; a supplementary program (e.g. 346,
    valid only together with 359/659) has none and is left out here.
    """
    wanted = set(split_code(hdo_code))
    return [
        i
        for p in programs
        if p["code"] in wanted
        for i in p["intervals"]
        if i.get("t_type") == "nt" and i.get("tarification")
    ]


# ----------------------------------------------------------------------------------------- schedule maths
def _minutes(text: str) -> int:
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime


def low_windows(intervals: list[dict[str, Any]], day: date, tz: Any = None, winter_time: bool = False) -> list[Window]:
    """The low-tariff windows of one local day, merged and sorted.

    Like the ZSDIS page, every day type (weekday / weekend) has its own 24-hour timeline: an interval over
    midnight such as 22:00-6:00 contributes 00:00-06:00 and 22:00-24:00 to each day it is valid for.
    A window ending at 24:00 and one starting at 00:00 of the next day are joined by :func:`windows_between`.

    ``winter_time``: the device ignores daylight saving, so in summer its clock is one hour behind the wall clock
    and every window lies one hour later.
    """
    weekend = day.weekday() >= 5
    spans: list[tuple[int, int]] = []
    for i in intervals:
        if not (i.get("weekend") if weekend else i.get("weekday")):
            continue
        start, end = _minutes(i["t_from"]), _minutes(i["t_to"])
        if end <= start:  # over midnight
            spans.append((0, end))
            spans.append((start, 24 * 60))
        else:
            spans.append((start, end))
    spans.sort()
    merged: list[list[int]] = []
    for start, end in spans:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    base = datetime.combine(day, time(0, 0), tzinfo=tz)
    shift = 0
    if winter_time and tz is not None and base.astimezone(tz).dst():
        shift = 60
    return [Window(_at(base, a + shift), _at(base, b + shift)) for a, b in merged]


def _at(midnight: datetime, minutes: int) -> datetime:
    """Wall-clock ``minutes`` after local midnight (correct across daylight-saving changes)."""
    naive = datetime.combine(midnight.date(), time(0, 0)) + timedelta(minutes=minutes)
    return naive.replace(tzinfo=midnight.tzinfo)


def windows_between(
    intervals: list[dict[str, Any]], start: datetime, end: datetime, tz: Any, winter_time: bool = False
) -> list[Window]:
    """Low-tariff windows around ``[start, end]`` (a day of margin on both sides), merged across midnight."""
    first = start.astimezone(tz).date() - timedelta(days=1)
    last = end.astimezone(tz).date() + timedelta(days=1)
    found: list[Window] = []
    day = first
    while day <= last:
        found += low_windows(intervals, day, tz, winter_time)
        day += timedelta(days=1)
    found.sort(key=lambda w: w.start)
    merged: list[Window] = []
    for w in found:
        if merged and w.start <= merged[-1].end:
            if w.end > merged[-1].end:
                merged[-1] = Window(merged[-1].start, w.end)
        else:
            merged.append(w)
    return merged


def windows_around(
    intervals: list[dict[str, Any]], now: datetime, tz: Any, winter_time: bool = False
) -> list[Window]:
    """Windows from the day before to two days after ``now``."""
    return windows_between(intervals, now - timedelta(days=1), now + timedelta(days=2), tz, winter_time)


def timeline(low: list[Window], start: datetime, end: datetime) -> list[tuple[bool, Window]]:
    """Alternating ``(is_low, window)`` segments that overlap ``[start, end]``; the ends are not clipped."""
    segments: list[tuple[bool, Window]] = []
    previous: Window | None = None
    for w in sorted(low, key=lambda w: w.start):
        if previous is not None and w.start > previous.end:
            segments.append((False, Window(previous.end, w.start)))
        segments.append((True, w))
        previous = w
    return [(is_low, w) for is_low, w in segments if w.end > start and w.start < end]


@dataclass(frozen=True)
class Status:
    low: bool
    changes_at: datetime | None  # when the tariff changes next
    next_low_start: datetime | None
    next_low_end: datetime | None


def status(windows: list[Window], now: datetime) -> Status:
    """Tariff now and the next change, from windows around ``now`` (see :func:`windows_around`)."""
    current = next((w for w in windows if w.start <= now < w.end), None)
    upcoming = [w for w in windows if w.start > now]
    next_start = upcoming[0].start if upcoming else None
    if current:
        return Status(True, current.end, next_start, current.end)
    return Status(False, next_start, next_start, upcoming[0].end if upcoming else None)


def high_windows(low: list[Window], day: date, tz: Any) -> list[Window]:
    """The high-tariff gaps of one local day (what is left of 00:00-24:00 outside the low windows)."""
    day_start = datetime.combine(day, time(0, 0), tzinfo=tz)
    day_end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=tz)
    gaps: list[Window] = []
    cursor = day_start
    for w in sorted(low, key=lambda w: w.start):
        if w.end <= day_start or w.start >= day_end:
            continue
        if w.start > cursor:
            gaps.append(Window(cursor, w.start))
        cursor = max(cursor, w.end)
    if cursor < day_end:
        gaps.append(Window(cursor, day_end))
    return gaps


# ------------------------------------------------------------------------------------------- snapshot
def _hhmm(moment: datetime, midnight_end: datetime | None = None) -> str:
    if midnight_end is not None and moment == midnight_end:
        return "24:00"
    return moment.strftime("%H:%M")


@dataclass(frozen=True)
class Snapshot:
    """Everything the entities show, for one moment."""

    low: bool
    changes_at: datetime | None
    next_low_start: datetime | None
    next_low_end: datetime | None
    low_today: tuple[str, ...]  # "00:15-06:30", clipped to the local day
    high_today: tuple[str, ...]
    high_tomorrow: tuple[str, ...]
    high_hours_today: float
    refresh_at: datetime  # next moment the state changes: a tariff change or local midnight


def _clip(windows: list[Window], day_start: datetime, day_end: datetime) -> list[Window]:
    clipped = []
    for w in sorted(windows, key=lambda w: w.start):
        start, end = max(w.start, day_start), min(w.end, day_end)
        if end > start:
            clipped.append(Window(start, end))
    return clipped


def snapshot(intervals: list[dict[str, Any]], now: datetime, tz: Any, winter_time: bool = False) -> Snapshot:
    """Tariff now, the next change and today's windows for a meter's low-tariff intervals."""
    now = now.astimezone(tz)
    low = windows_around(intervals, now, tz, winter_time)
    state = status(low, now)
    today = now.date()
    day_start = datetime.combine(today, time(0, 0), tzinfo=tz)
    day_end = datetime.combine(today + timedelta(days=1), time(0, 0), tzinfo=tz)
    low_today = _clip(low, day_start, day_end)
    high_today = high_windows(low, today, tz)
    high_tomorrow = high_windows(low, today + timedelta(days=1), tz)
    next_end = datetime.combine(today + timedelta(days=2), time(0, 0), tzinfo=tz)

    def fmt(ws: list[Window], tomorrow: bool = False) -> tuple[str, ...]:
        end_mark = next_end if tomorrow else day_end
        return tuple(f"{_hhmm(w.start)}-{_hhmm(w.end, end_mark)}" for w in ws)

    hours = sum((w.end - w.start).total_seconds() for w in high_today) / 3600
    refresh = min(state.changes_at, day_end) if state.changes_at else day_end
    return Snapshot(
        low=state.low,
        changes_at=state.changes_at,
        next_low_start=state.next_low_start,
        next_low_end=state.next_low_end,
        low_today=fmt(low_today),
        high_today=fmt(high_today),
        high_tomorrow=fmt(high_tomorrow, True),
        high_hours_today=round(hours, 2),
        refresh_at=refresh,
    )
