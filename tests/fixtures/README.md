# HTML regression fixtures

## Issue #6: German SOLPLUS 55 basic menu

`issue_6_solplus_55_fw_2_65_de.html` contains the complete HTML posted by Pocket74
in [issue #6](https://github.com/Ralleberg/solutronic/issues/6) on 8 October 2026.
The snapshot preserves the source markup, including malformed table attributes,
whitespace, and HTML entities, with one trailing newline added to the file.

| Reading | Expected value |
| --- | --- |
| Leistung AC (`PAC`) | 313 W |
| Netzspannung (`UACL1`) | 234 V |
| Gleichspannung (`UDC1`) | 385 V |
| Energie Tag (`ET`) | 2.102 kWh |
| Energie gesamt (`EG`) | 103023 kWh |
| Model | SOLPLUS 55 |
| Serial number | 22031 |
| Firmware | 2.65 |

The page has one inverter identity and one set of readings. Its navigation links
and SPP address are not evidence of individual slave readings. No currents,
efficiency, maximum power, or phase-specific power are present in this sample.
The German parser must not synthesize those fields. The existing English legacy
parser's historical L1 power alias remains unchanged.

Tests cover parsing, setup validation, coordinator metadata, the exact sensor
set and identity, and persisted energy state across restart. HTML-fixture
verification has not yet been confirmed on physical hardware. Individual RS485
slave support requires additional page samples and access details.

## Issue #6 follow-up: HTTP character decoding

Pocket74's [10 October 2026 comment](https://github.com/Ralleberg/solutronic/issues/6#issuecomment-6096096884)
reports `UnicodeDecodeError` for byte `0xfc` in `aiohttp.ClientResponse.text()`,
before the integration's HTML parser runs. `test_http_encoding.py` encodes the
original fixture as ISO-8859-1 and Windows-1252 and serves those bytes over local
HTTP. This recreates the failing decoding path while preserving the known readings.
The raw HTTP headers and body from the affected inverter have not been supplied;
the replay is a constructed regression case, not a captured response.

All seven attached PktMon text exports were inspected, including their hex packet
bytes. Their IPv4 TCP traffic uses port 33330, with no port-80/8888 HTTP exchange
or HTTP/HTML payloads. They contain binary protocol exchanges and cannot establish
the HTTP charset, slave page selection, or the meaning of individual measurement
fields. No protocol writes, slave commands, or guessed measurement mappings are
implemented. Raw captures are not included in this repository.
