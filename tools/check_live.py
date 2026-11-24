"""End-to-end check of the integration's client + parser WITHOUT Home Assistant.

Signs in with your ZSE e-mail/password (password prompt is hidden, nothing is
stored), fetches everything the sensors use (read-only calls) and prints the
values the sensors would show.

Run from the repository root:
    python tools/check_live.py
Needs:  pip install aiohttp
"""
from __future__ import annotations

import asyncio
import getpass
import importlib
import os
import pathlib
import sys
import types
from datetime import date

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load custom_components/zse_energia as a package named "zse_energia" without
# executing its __init__.py (which imports Home Assistant).
PKG_DIR = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "zse_energia"
pkg = types.ModuleType("zse_energia")
pkg.__path__ = [str(PKG_DIR)]
sys.modules["zse_energia"] = pkg
api = importlib.import_module("zse_energia.api")
parser = importlib.import_module("zse_energia.parser")

import aiohttp  # noqa: E402


def show(title: str, obj: dict) -> None:
    print(f"\n--- {title}")
    for k, v in obj.items():
        print(f"  {k:28} {v}")


def print_history(h: dict) -> None:
    print("\n--- Payment history (EUR)  since", h["since"])
    cols = ("advances", "settlements", "other", "refunds", "paid", "net")
    print("  year  " + "".join(f"{c:>13}" for c in cols))
    for y in h["yearly"]:
        print(f"  {y['year']}  " + "".join(f"{y[c]:>13.2f}" for c in cols))
    t = h["totals"]
    print("  total " + "".join(f"{t[c]:>13.2f}" for c in cols))
    print("\n--- Statistics that would be imported (rows incl. baseline)")
    series = dict(h["series"], consumption=h["consumption"])
    for key, pts in series.items():
        rows = parser.cumulative(pts)
        last = rows[-1][2] if rows else 0
        print(f"  {key:18} {len(rows) + (1 if rows else 0):4} rows, final sum {last:.2f}")


async def main() -> None:
    email = os.environ.get("ZSE_EMAIL") or input("ZSE e-mail: ").strip()
    password = os.environ.get("ZSE_PASSWORD") or getpass.getpass("ZSE password (hidden): ")
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        client = api.ZseClient(session, email, password)
        try:
            await client.async_login()
        except api.ZseAuthError as err:
            sys.exit(f"Sign-in rejected: {err}")
        print("Sign-in OK. Token valid for about "
              f"{(client._expires - __import__('time').time()) / 3600:.1f} h")
        raw = await api.async_fetch_raw(client)

    print("\nRaw call results:")
    for k, v in raw.items():
        n = len(v) if isinstance(v, (list, dict)) else v
        print(f"  {k:12} {'MISSING' if v is None else 'ok'} ({n})")

    data = parser.build(raw, date.today())
    show("Partner level", data["partner"])
    for zu, acc in data["accounts"].items():
        shown = {k: v for k, v in acc.items() if k not in ("zu", "history")}
        if shown.get("last_settlement"):
            shown["last_settlement"] = {
                k: v for k, v in shown["last_settlement"].items() if k != "invoice"
            }
        show(f"Account {zu[:2]}…{zu[-3:]}", shown)
        print_history(acc["history"])


if __name__ == "__main__":
    asyncio.run(main())
