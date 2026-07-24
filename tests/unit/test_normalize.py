"""Tests for utils.normalize() — Unicode NFC folding, lot B.

NFC unifies precomposed vs decomposed (NFD) representations of the same text so
they yield one identity key, while never stripping accents (no folding).
"""

import unicodedata

from utils import make_normalized_key, normalize


class TestNFCFolding:
    def test_precomposed_and_decomposed_are_equal(self):
        """"Zoë" precomposed (U+00EB) and decomposed ("e" + U+0308, the NFD form
        a Rekordbox macOS export produces) must normalize to the same key."""
        nfc = unicodedata.normalize("NFC", "Zoë")
        nfd = unicodedata.normalize("NFD", "Zoë")
        # Sanity: the two source strings really differ byte-for-byte.
        assert nfc != nfd
        assert normalize(nfc) == normalize(nfd)

    def test_decomposed_literal_matches_precomposed(self):
        """Same check built from explicit code points, no unicodedata helper."""
        precomposed = "Zoë"  # Z o ë
        decomposed = "Zoë"  # Z o e + combining diaeresis
        assert precomposed != decomposed
        assert normalize(precomposed) == normalize(decomposed)

    def test_output_is_nfc(self):
        """normalize() always returns text in NFC form."""
        out = normalize("Zoë")
        assert out == unicodedata.normalize("NFC", out)


class TestKeyStability:
    def test_make_normalized_key_stable_across_composition(self):
        """make_normalized_key is invariant to composition on accented titles."""
        nfc_title = unicodedata.normalize("NFC", "Café del Mar")
        nfd_title = unicodedata.normalize("NFD", "Café del Mar")
        nfc_artist = unicodedata.normalize("NFC", "José González")
        nfd_artist = unicodedata.normalize("NFD", "José González")
        assert make_normalized_key(nfc_title, nfc_artist) == make_normalized_key(
            nfd_title, nfd_artist
        )

    def test_make_normalized_key_none_artist(self):
        """A None artist stays supported (equivalent to empty string)."""
        assert make_normalized_key("Café", None) == make_normalized_key("Café", "")


class TestNoAccentFolding:
    def test_accents_are_not_stripped(self):
        """Guard rail: NFC must NOT remove accents. Accented and un-accented
        spellings stay DISTINCT keys ("err toward separation")."""
        assert normalize("León") != normalize("Leon")

    def test_cedilla_not_stripped(self):
        assert normalize("França") != normalize("Franca")
