"""Names of the long-term statistics (no Home Assistant imports, so it can be tested on its own).

A statistic id is ``zse_energia:<object id>``. The object id is built from the series and the kind of
contract, e.g. ``net_paid_electricity`` / ``net_paid_gas``: the same on every installation, so a
ready-made dashboard works without editing. Only when one login has several contract accounts of the
same kind (or when the option "account number in statistic names" is on) the account number is added,
e.g. ``net_paid_electricity_6300000001``, so that they do not overwrite each other.

Versions before 0.5.0 used ``<series>_<account number>`` only; that form is "legacy" and is cleaned up.
"""
from __future__ import annotations

import re


def kind_slug(kind: str) -> str:
    """``"electricity"`` -> ``"electricity"``; anything else becomes a safe lowercase word."""
    return re.sub(r"[^a-z0-9]+", "_", (kind or "").lower()).strip("_") or "other"


def object_id(key: str, kind: str, zu: str, with_number: bool) -> str:
    """The part of the statistic id after ``zse_energia:``."""
    base = f"{key}_{kind_slug(kind)}"
    return f"{base}_{zu}" if with_number else base


def legacy_object_id(key: str, zu: str) -> str:
    """Before 0.5.0: ``advances_paid_6300000001``."""
    return f"{key}_{zu}"


def numbers_needed(accounts: dict[str, dict]) -> set[str]:
    """Account numbers that must carry the number in their ids: several accounts of one kind in one login."""
    by_kind: dict[str, list[str]] = {}
    for zu, account in accounts.items():
        by_kind.setdefault(kind_slug(account.get("kind", "electricity")), []).append(zu)
    return {zu for zus in by_kind.values() if len(zus) > 1 for zu in zus}


def obsolete_object_ids(keys: list[str], kind: str, zu: str, with_number: bool) -> list[str]:
    """Ids of older naming schemes of this account, removed so that no orphan remains.

    The id without the number is never listed: it may belong to another account of the same kind.
    """
    other = {legacy_object_id(k, zu) for k in keys}
    if not with_number:
        other |= {object_id(k, kind, zu, True) for k in keys}
    return sorted(other)
