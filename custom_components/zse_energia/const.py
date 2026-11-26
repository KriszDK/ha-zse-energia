"""Constants for the ZSE Energia integration."""
from __future__ import annotations

DOMAIN = "zse_energia"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_PARTNER = "partner"
CONF_SCAN_HOURS = "scan_hours"
CONF_HDO_WINTER_TIME = "hdo_winter_time"
CONF_STAT_NUMBER = "statistics_with_account_number"

DEFAULT_SCAN_HOURS = 6
MIN_SCAN_HOURS = 1
MAX_SCAN_HOURS = 24

SITE_URL = "https://www.zse.sk"
B2C_HOST = "https://zseenergia.b2clogin.com"
B2C_PROVIDER_ID = "LocalAccountSigninEmailExchange"
DATA_SERVICE = "IZsedisatDataApi"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
