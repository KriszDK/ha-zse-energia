"""Offline tests for api.py: which headers survive a redirect (needs aiohttp, skipped without it)."""
from __future__ import annotations

import importlib
import pathlib
import sys
import types
import unittest

try:
    import aiohttp  # noqa: F401
    from yarl import URL
except ImportError:  # pragma: no cover - aiohttp is not installed
    URL = None

api = None
if URL is not None:
    # load custom_components/zse_energia as a package without its __init__.py (Home Assistant imports)
    PKG_DIR = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "zse_energia"
    pkg = types.ModuleType("zse_energia")
    pkg.__path__ = [str(PKG_DIR)]
    sys.modules.setdefault("zse_energia", pkg)
    api = importlib.import_module("zse_energia.api")

HEADERS = {"Authorization": "Bearer t", "X-CSRF-TOKEN": "c", "Accept": "application/json"}


@unittest.skipIf(api is None, "aiohttp is not installed")
class RedirectHeaderTests(unittest.TestCase):
    def test_same_https_origin_keeps_everything(self) -> None:
        kept = api._redirect_headers(HEADERS, URL("https://www.zse.sk/a"), URL("https://www.zse.sk/b"))
        self.assertEqual(kept, HEADERS)

    def test_other_host_drops_credentials(self) -> None:
        kept = api._redirect_headers(HEADERS, URL("https://www.zse.sk/a"), URL("https://evil.example/b"))
        self.assertEqual(kept, {"Accept": "application/json"})

    def test_plain_http_drops_credentials(self) -> None:
        kept = api._redirect_headers(HEADERS, URL("https://www.zse.sk/a"), URL("http://www.zse.sk/b"))
        self.assertEqual(kept, {"Accept": "application/json"})

    def test_cookies_only_over_https(self) -> None:
        client = api.ZseClient(None, "e", "p")  # type: ignore[arg-type]
        client._cookies["www.zse.sk"] = {"s": "1"}
        self.assertEqual(client._cookie_header(URL("https://www.zse.sk/")), "s=1")
        self.assertIsNone(client._cookie_header(URL("http://www.zse.sk/")))


if __name__ == "__main__":
    unittest.main()
