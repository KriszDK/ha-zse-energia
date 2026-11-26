"""Calendar of the low / high tariff periods."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import ZseConfigEntry, ZseCoordinator
from .hdo import Window, split_code, timeline, windows_between
from .hdo_entity import ZseHdoEntity
from .texts import TEXTS, pick_language


class ZseTariffCalendar(ZseHdoEntity, CalendarEntity):
    """Low and high tariff periods as calendar events (handy on a dashboard and for automations)."""

    _attr_translation_key = "tariff_calendar"

    def __init__(self, coordinator: ZseCoordinator, zu: str) -> None:
        super().__init__(coordinator, zu, "tariff_calendar")

    def _segments(self, start: datetime, end: datetime) -> list[tuple[bool, Window]]:
        intervals = self.coordinator.hdo.intervals_for(self._hdo_code)
        low = windows_between(intervals, start, end, dt_util.get_default_time_zone(), self._winter_time)
        return timeline(low, start, end)

    def _event(self, is_low: bool, window: Window) -> CalendarEvent:
        texts = TEXTS[pick_language(self.hass.config.language)]
        return CalendarEvent(
            start=window.start, end=window.end, summary=texts["cal_low" if is_low else "cal_high"]
        )

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        for is_low, window in self._segments(now - timedelta(days=1), now + timedelta(days=1)):
            if window.start <= now < window.end:
                return self._event(is_low, window)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [self._event(is_low, window) for is_low, window in self._segments(start_date, end_date)]


async def async_setup_entry(
    hass: HomeAssistant, entry: ZseConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the tariff calendar of every contract account that has an HDO code."""
    coordinator = entry.runtime_data
    async_add_entities(
        ZseTariffCalendar(coordinator, zu)
        for zu, account in (coordinator.data or {}).get("accounts", {}).items()
        if split_code(account.get("hdo_code"))
    )
