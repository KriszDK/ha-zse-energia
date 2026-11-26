"""The ZSE Energia integration (unofficial)."""
from __future__ import annotations

from datetime import timedelta

import aiohttp

from homeassistant.const import EVENT_CORE_CONFIG_UPDATE, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .api import ZseClient
from .const import CONF_EMAIL, CONF_PARTNER, CONF_PASSWORD, DOMAIN
from .coordinator import ZseConfigEntry, ZseCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ZseConfigEntry) -> bool:
    """Set up from a config entry."""
    # ZseClient keeps the sign-in cookies itself (see api.py), so the session must not
    session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
    client = ZseClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    client.partner = entry.data.get(CONF_PARTNER)

    coordinator = ZseCoordinator(hass, entry, client)
    await coordinator.hdo.async_load()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(session.close)

    # Entity names, statistic names and the dashboard texts follow the system language: when it is
    # changed (Settings -> System -> General), reload so that they are rewritten right away.
    language = hass.config.language

    @callback
    def _config_updated(event: Event) -> None:
        if hass.config.language != language:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, _config_updated))
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    # the low/high tariff table: checked right away and then twice a day; downloaded at most monthly
    async def _refresh_hdo(_now: object = None) -> None:
        await coordinator.hdo.async_refresh_if_due()

    entry.async_create_background_task(hass, _refresh_hdo(), f"{DOMAIN} HDO table")
    entry.async_on_unload(async_track_time_interval(hass, _refresh_hdo, timedelta(hours=12)))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZseConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: ZseConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
