"""
Tests for the Rekordbox XML validator/parser (A6-03: defusedxml hardening).

Focus: the parser must reject XML entity-expansion payloads ("billion laughs")
instead of expanding them into gigabytes of memory / hanging the web worker.
"""
import pytest
from defusedxml.common import DefusedXmlException

from services.rekordbox_xml import parse_rekordbox_xml, validate_rekordbox_xml

# Classic "billion laughs" entity-expansion payload (small on disk, would blow up
# in memory with a naive parser). With defusedxml this raises EntitiesForbidden.
BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
 <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
 <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
]>
<DJ_PLAYLISTS Version="1.0.0">&lol5;</DJ_PLAYLISTS>"""


class TestValidateRekordboxXml:
    def test_valid_export_accepted(self):
        content = (
            b'<DJ_PLAYLISTS Version="1.0.0"><COLLECTION></COLLECTION></DJ_PLAYLISTS>'
        )
        assert validate_rekordbox_xml(content) is True

    def test_wrong_root_rejected(self):
        assert validate_rekordbox_xml(b'<OTHER Version="1.0.0"/>') is False

    def test_missing_version_rejected(self):
        assert validate_rekordbox_xml(b"<DJ_PLAYLISTS/>") is False

    def test_malformed_xml_rejected(self):
        assert validate_rekordbox_xml(b"<not closed") is False

    def test_billion_laughs_returns_false_without_hang(self):
        # Must return False (defusedxml raises EntitiesForbidden, caught inside
        # validate) and return promptly — no exponential entity expansion.
        assert validate_rekordbox_xml(BILLION_LAUGHS) is False


class TestParseRekordboxXml:
    def test_parse_valid_collection(self):
        content = (
            b'<DJ_PLAYLISTS Version="1.0.0"><COLLECTION>'
            b'<TRACK TrackID="1" Name="Wannabe" Artist="VOLAC" AverageBpm="128.0"/>'
            b"</COLLECTION></DJ_PLAYLISTS>"
        )
        tracks = parse_rekordbox_xml(content)
        assert len(tracks) == 1
        assert tracks[0].id == 1
        assert tracks[0].title == "Wannabe"

    def test_parse_raises_on_entity_expansion(self):
        # defusedxml refuses the entities instead of expanding them: the worker
        # gets a clean exception rather than a memory blow-up / hang.
        with pytest.raises(DefusedXmlException):
            parse_rekordbox_xml(BILLION_LAUGHS)
