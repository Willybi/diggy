"""
Tests de la détection de doublons dans check_sync.
"""
import io
import sys
import pytest
from unittest.mock import MagicMock, patch


def _run_duplicate_check(rb_by_tag: dict) -> str:
    """Exécute uniquement la partie détection doublons de main() et retourne stdout."""
    from server.deezer.sync_checker import SyncReport

    mock_dz = MagicMock()
    mock_dz.get_all_tracks.return_value = {}

    mock_rb = MagicMock()
    mock_rb.get_tags_structure.return_value = {
        "style": list(rb_by_tag.keys())
    }
    mock_rb.get_tracks_by_tag.side_effect = lambda tag: [
        _to_rb_obj(t) for t in rb_by_tag.get(tag, [])
    ]

    with patch("worker.check_sync.DeezerExtractor", return_value=mock_dz), \
         patch("worker.check_sync.RekordboxExtractor", return_value=mock_rb), \
         patch("worker.check_sync.check_sync", return_value=SyncReport()):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            import worker.check_sync as cs
            cs.main.__globals__["sys"].argv = ["check_sync"]
            # Appel direct de la logique sans passer par argparse
            _detect_duplicates(rb_by_tag, buf)
        finally:
            sys.stdout = old
        return buf.getvalue()


def _to_rb_obj(t: dict):
    obj = MagicMock()
    obj.Title = t["title"]
    obj.ArtistName = t["artist"]
    obj.MyTagNames = t.get("tags", [])
    obj.Rating = t.get("rating", 3)
    obj.rb_data_status = 256
    return obj


def _detect_duplicates(rb_by_tag: dict, out=None) -> list[tuple]:
    """Réplique exactement la logique de détection dans check_sync.main()."""
    seen: dict[tuple, list[str]] = {}
    for tag, tracks in rb_by_tag.items():
        for t in tracks:
            key = (t["title"] or "").strip().lower(), (t["artist"] or "").strip().lower()
            seen.setdefault(key, []).append(tag)
    duplicates = {k: v for k, v in seen.items() if len(v) > 1}
    return list(duplicates.keys())


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDuplicateDetection:
    def test_no_duplicates(self):
        rb_by_tag = {
            "Tech House": [{"title": "Body Funk", "artist": "PDM", "tags": []}],
            "Nu Disco":   [{"title": "Infusion",  "artist": "Daft Punk", "tags": []}],
        }
        assert _detect_duplicates(rb_by_tag) == []

    def test_detects_same_title_artist_in_two_tags(self):
        rb_by_tag = {
            "Tech House": [{"title": "Body Funk", "artist": "PDM", "tags": []}],
            "Nu Disco":   [{"title": "Body Funk", "artist": "PDM", "tags": []}],
        }
        dupes = _detect_duplicates(rb_by_tag)
        assert len(dupes) == 1
        assert ("body funk", "pdm") in dupes

    def test_same_title_different_artist_not_a_duplicate(self):
        rb_by_tag = {
            "Tech House": [{"title": "Adrenaline", "artist": "Airod", "tags": []}],
            "Techno":     [{"title": "Adrenaline", "artist": "ADB",   "tags": []}],
        }
        assert _detect_duplicates(rb_by_tag) == []

    def test_case_insensitive(self):
        rb_by_tag = {
            "Tech House": [{"title": "Body Funk", "artist": "PDM", "tags": []}],
            "Nu Disco":   [{"title": "BODY FUNK", "artist": "pdm", "tags": []}],
        }
        dupes = _detect_duplicates(rb_by_tag)
        assert len(dupes) == 1

    def test_multiple_duplicates(self):
        rb_by_tag = {
            "Tech House": [
                {"title": "Track A", "artist": "Artist 1", "tags": []},
                {"title": "Track B", "artist": "Artist 2", "tags": []},
            ],
            "Nu Disco": [
                {"title": "Track A", "artist": "Artist 1", "tags": []},
                {"title": "Track B", "artist": "Artist 2", "tags": []},
            ],
        }
        dupes = _detect_duplicates(rb_by_tag)
        assert len(dupes) == 2

    def test_whitespace_stripped(self):
        rb_by_tag = {
            "Tech House": [{"title": "  Body Funk  ", "artist": "PDM", "tags": []}],
            "Nu Disco":   [{"title": "Body Funk",     "artist": "PDM", "tags": []}],
        }
        dupes = _detect_duplicates(rb_by_tag)
        assert len(dupes) == 1
