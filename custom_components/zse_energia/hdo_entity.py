"""Base class of the low/high tariff entities.

They are not polled: each one asks for a state update at the exact moment the tariff changes (and at midnight,
when "today" changes), and again when the tariff table or the meter's HDO code changes.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .const import CONF_HDO_WINTER_TIME
from .entity import ZseEntity
from .hdo import Snapshot, snapshot, split_code


class ZseHdoEntity(ZseEntity):
    """Entity of one contract account whose state follows the tariff schedule of its meter."""

    _unsub_timer: CALLBACK_TYPE | None = None

    @property
    def _hdo_code(self) -> Any:
        return (self._account or {}).get("hdo_code")

    @property
    def _winter_time(self) -> bool:
        return bool(self.coordinator.config_entry.options.get(CONF_HDO_WINTER_TIME, False))

    @property
    def _programs(self) -> list[int]:
        return split_code(self._hdo_code)

    def _snapshot(self, now: datetime | None = None) -> Snapshot | None:
        intervals = self.coordinator.hdo.intervals_for(self._hdo_code)
        if not intervals:
            return None
        return snapshot(intervals, now or dt_util.now(), dt_util.get_default_time_zone(), self._winter_time)

    @property
    def available(self) -> bool:
        return super().available and self._snapshot() is not None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.hdo.add_listener(self._tables_changed))
        self._schedule()

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_timer()
        await super().async_will_remove_from_hass()

    # ------------------------------------------------------------------------------------- scheduling
    @callback
    def _cancel_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def _schedule(self) -> None:
        self._cancel_timer()
        snap = self._snapshot()
        if snap is not None:
            self._unsub_timer = async_track_point_in_time(
                self.hass, self._timer_fired, snap.refresh_at + timedelta(seconds=1)
            )

    @callback
    def _timer_fired(self, _now: datetime) -> None:
        self._unsub_timer = None
        self._tables_changed()

    @callback
    def _tables_changed(self) -> None:
        self.async_write_ha_state()
        self._schedule()

    @callback
    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()
        self._schedule()
