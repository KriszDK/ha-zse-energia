"""Config flow for ZSE Energia."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ZseAuthError, ZseClient, ZseConnectionError, ZseError
from .const import (
    CONF_EMAIL,
    CONF_PARTNER,
    CONF_PASSWORD,
    CONF_HDO_WINTER_TIME,
    CONF_SCAN_HOURS,
    DEFAULT_SCAN_HOURS,
    DOMAIN,
    MAX_SCAN_HOURS,
    MIN_SCAN_HOURS,
)

_LOGGER = logging.getLogger(__name__)

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _validate(hass: HomeAssistant, email: str, password: str) -> str:
    """Sign in once; return the partner number."""
    session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
    try:
        client = ZseClient(session, email, password)
        await client.async_login()
        assert client.partner
        return client.partner
    finally:
        await session.close()


class ZseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def _try(self, email: str, password: str) -> tuple[str | None, dict[str, str]]:
        try:
            return await _validate(self.hass, email, password), {}
        except ZseAuthError:
            return None, {"base": "invalid_auth"}
        except ZseConnectionError:
            return None, {"base": "cannot_connect"}
        except ZseError:
            _LOGGER.exception("Unexpected ZSE portal response")
            return None, {"base": "portal_changed"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error")
            return None, {"base": "unknown"}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            partner, errors = await self._try(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            if partner:
                await self.async_set_unique_id(partner)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"ZSE ({user_input[CONF_EMAIL]})",
                    data={**user_input, CONF_PARTNER: partner},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL, default=(user_input or {}).get(CONF_EMAIL, "")): str,
                    vol.Required(CONF_PASSWORD): _PASSWORD,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            partner, errors = await self._try(entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            if partner:
                if partner != entry.unique_id:
                    return self.async_abort(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        return ZseOptionsFlow()


class ZseOptionsFlow(OptionsFlow):
    """Options: polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_HOURS: int(user_input[CONF_SCAN_HOURS]),
                    CONF_HDO_WINTER_TIME: bool(user_input.get(CONF_HDO_WINTER_TIME, False)),
                }
            )
        current = self.config_entry.options.get(CONF_SCAN_HOURS, DEFAULT_SCAN_HOURS)
        winter = self.config_entry.options.get(CONF_HDO_WINTER_TIME, False)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_HOURS, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_HOURS,
                            max=MAX_SCAN_HOURS,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="h",
                        )
                    ),
                    vol.Required(CONF_HDO_WINTER_TIME, default=winter): bool,
                }
            ),
        )
