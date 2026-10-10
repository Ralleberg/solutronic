"""Replay legacy HTTP bytes through aiohttp without contacting an inverter."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.helpers import frame

from custom_components.solutronic import solutronic_api as api
from custom_components.solutronic.config_flow import SolutronicInverterConfigFlow

ISSUE_HTML = (
    Path(__file__).parent / "fixtures" / "issue_6_solplus_55_fw_2_65_de.html"
).read_text(encoding="utf-8")
EXPECTED = {
    "PAC": 313,
    "UACL1": 234,
    "UDC1": 385,
    "ET": 2.102,
    "EG": 103023,
    "SN": "22031",
}


class HttpEncodingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.body = ISSUE_HTML.encode("iso-8859-1")
        self.content_type = "text/html"
        self.status = 200
        self.requests = 0
        app = web.Application()
        app.router.add_get("/", self.respond)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.addAsyncCleanup(self.runner.cleanup)
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = self.runner.addresses[0][1]
        self.url = f"http://127.0.0.1:{self.port}/"
        self.session = aiohttp.ClientSession()
        self.addAsyncCleanup(self.session.close)
        api._BASE_URL_CACHE.clear()
        self.addCleanup(api._BASE_URL_CACHE.clear)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hass = HomeAssistant(self.directory.name)
        if hasattr(frame, "async_setup"):
            frame.async_setup(self.hass)
        self.hass.config_entries = SimpleNamespace(async_update_entry=Mock())

    async def respond(self, request):
        self.requests += 1
        return web.Response(
            body=self.body,
            status=self.status,
            headers={"Content-Type": self.content_type},
        )

    async def fetch(self):
        return await api._fetch_text(
            self.session, self.url, aiohttp.ClientTimeout(total=5)
        )

    async def test_issue_6_legacy_bytes_decode_without_charset(self):
        # 0xfc is the reported invalid UTF-8 byte; the original HTML contains ü.
        self.assertIn(b"\xfc", self.body)
        with self.assertRaises(UnicodeDecodeError):
            self.body.decode("utf-8")
        self.assertEqual(await self.fetch(), ISSUE_HTML)
        self.assertEqual(self.requests, 1)

    async def test_issue_6_legacy_bytes_with_wrong_utf8_header(self):
        self.content_type = "text/html; charset=utf-8"
        self.assertEqual(await self.fetch(), ISSUE_HTML)
        self.assertEqual(self.requests, 1)

    async def test_explicit_legacy_charsets_remain_supported(self):
        for charset in ("iso-8859-1", "windows-1252"):
            with self.subTest(charset=charset):
                self.body = ISSUE_HTML.encode(charset)
                self.content_type = f"text/html; charset={charset}"
                self.assertEqual(await self.fetch(), ISSUE_HTML)

    async def test_utf8_remains_unchanged(self):
        for content_type in ("text/html", "text/html; charset=utf-8"):
            with self.subTest(content_type=content_type):
                self.content_type = content_type
                self.body = (ISSUE_HTML + "<p>€ — 中文</p>").encode("utf-8")
                self.assertEqual(await self.fetch(), ISSUE_HTML + "<p>€ — 中文</p>")

    async def test_explicit_nonwestern_charset_is_respected(self):
        self.body = "<p>SOLPLUS 日本語</p>".encode("shift_jis")
        self.content_type = "text/html; charset=shift_jis"
        self.assertEqual(await self.fetch(), "<p>SOLPLUS 日本語</p>")

    async def test_windows_1252_punctuation_is_preserved(self):
        self.body = (ISSUE_HTML + "<p>€ —</p>").encode("windows-1252")
        self.assertEqual(await self.fetch(), ISSUE_HTML + "<p>€ —</p>")

    async def test_latin1_control_bytes_do_not_crash_decoding(self):
        self.body += b"<!--\x81-->"
        self.assertEqual(await self.fetch(), ISSUE_HTML + "<!--\x81-->")

    async def test_http_errors_are_not_hidden_by_encoding_fallback(self):
        self.status = 503
        with self.assertRaises(aiohttp.ClientResponseError) as error:
            await self.fetch()
        self.assertEqual(error.exception.status, 503)
        self.assertEqual(self.requests, 1)

    async def test_issue_6_setup_and_cached_poll_use_real_legacy_http_bytes(self):
        flow = SolutronicInverterConfigFlow()
        flow.hass = self.hass
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = Mock()
        with (
            patch.object(api, "PORTS_TO_TRY", (self.port,)),
            patch.object(api, "PATHS_TO_TRY", ("/",)),
            patch.object(api, "async_get_clientsession", return_value=self.session),
        ):
            result = await flow.async_step_manual({"ip_address": "127.0.0.1"})
            self.assertEqual(result["type"], "create_entry")
            self.assertEqual(result["data"], {"ip_address": "127.0.0.1"})
            flow.async_set_unique_id.assert_awaited_once_with("127.0.0.1")
            self.assertEqual(api.get_cached_base_url("127.0.0.1"), self.url)
            requests_before_poll = self.requests
            data, html = await api.async_get_sensor_snapshot("127.0.0.1", self.hass)
            self.assertEqual(data, EXPECTED)
            self.assertEqual(html, ISSUE_HTML)
            self.assertEqual(self.requests, requests_before_poll + 1)

    async def test_unrelated_legacy_bytes_are_still_rejected(self):
        self.body = "<p>Keine gültigen Messwerte</p>".encode("iso-8859-1")
        api._BASE_URL_CACHE["127.0.0.1"] = self.url
        with patch.object(api, "async_get_clientsession", return_value=self.session):
            with self.assertRaises(api.SolutronicInvalidResponseError):
                await api.async_get_sensor_snapshot("127.0.0.1", self.hass)

    async def test_english_legacy_http_retains_phase_alias(self):
        html = "<h1>SOLPLUS 25</h1><p>power AC: 1250 W<br>energy today: 2,5 kWh</p>"
        self.body = html.encode("utf-8")
        api._BASE_URL_CACHE["127.0.0.1"] = self.url
        with patch.object(api, "async_get_clientsession", return_value=self.session):
            data, decoded = await api.async_get_sensor_snapshot("127.0.0.1", self.hass)
        self.assertEqual(decoded, html)
        self.assertEqual(data, {"PAC": 1250, "PACL1": 1250, "ET": 2.5})

    async def test_modern_utf8_table_http_retains_readings(self):
        html = (
            "<h1>SOLPLUS 100 — 中文</h1><table>"
            "<tr><td>Power</td><td>PACL1</td><td>W</td><td>1250</td></tr>"
            "<tr><td>Energy</td><td>ET</td><td>kWh</td><td>2,5</td></tr></table>"
        )
        self.body = html.encode("utf-8")
        api._BASE_URL_CACHE["127.0.0.1"] = self.url
        with patch.object(api, "async_get_clientsession", return_value=self.session):
            data, decoded = await api.async_get_sensor_snapshot("127.0.0.1", self.hass)
        self.assertEqual(decoded, html)
        self.assertEqual(data, {"PACL1": 1250, "ET": 2.5})
