"""Unit tests for the pure ISRC entry-block helpers (workers.isrc_block)."""
import os
import sys

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from workers.isrc_block import (  # noqa: E402
    DEFAULT_BLOCKED_PREFIXES,
    ENV_VAR,
    blocked_prefixes,
    is_blocked_isrc,
)


def test_default_prefixes(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert blocked_prefixes() == ("GXLE", "GXLF", "KRB92")
    assert DEFAULT_BLOCKED_PREFIXES == "GXLE,GXLF,KRB92"
    assert is_blocked_isrc("GXLE12345678")
    assert is_blocked_isrc("KRB9200001")
    assert not is_blocked_isrc("FRZ110000001")
    # broader registrant prefixes are deliberately NOT blocked
    assert not is_blocked_isrc("QZ1234567890")
    assert not is_blocked_isrc("QT1234567890")


def test_custom_env_spaces_and_case(monkeypatch):
    monkeypatch.setenv(ENV_VAR, " abcd , ,XY12 ")
    assert blocked_prefixes() == ("ABCD", "XY12")
    assert is_blocked_isrc("abcd0001")
    assert is_blocked_isrc("XY120001")
    assert not is_blocked_isrc("GXLE0001")


def test_empty_env_disables(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "")
    assert blocked_prefixes() == ()
    assert not is_blocked_isrc("GXLE0001")
    monkeypatch.setenv(ENV_VAR, " , ")
    assert blocked_prefixes() == ()


def test_case_insensitive_isrc(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert is_blocked_isrc("gxlf0001")
    assert is_blocked_isrc("  gxle0001  ")


def test_none_and_empty_isrc():
    assert not is_blocked_isrc(None)
    assert not is_blocked_isrc("")
    assert not is_blocked_isrc("   ")
    assert not is_blocked_isrc(123)


def test_explicit_prefixes_override_env(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "")
    assert is_blocked_isrc("GXLE0001", prefixes=["gxle"])
    assert not is_blocked_isrc("GXLE0001", prefixes=[])
