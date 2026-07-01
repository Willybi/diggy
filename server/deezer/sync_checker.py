import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from dataclasses import dataclass, field
from enum import Enum

from utils import normalize as _normalize


class FlagType(str, Enum):
    DOWNLOAD_NEEDED = (
        "DOWNLOAD_NEEDED"  # Sur Deezer, absent de RB → télécharger via Deemix
    )
    ANOMALY = "ANOMALY"  # Dans RB, absent de Deezer → à investiguer
    MISPLACED = "MISPLACED"  # Présent des deux côtés mais mauvaise catégorie
    INFO = "INFO"  # Potentiellement indispo sur Deezer


@dataclass
class SyncFlag:
    flag: FlagType
    title: str
    artist: str
    deezer_playlist: str | None = None
    rb_tag: str | None = None
    expected_deezer_playlist: str | None = None  # pour MISPLACED
    expected_rb_tag: str | None = None  # pour MISPLACED


@dataclass
class SyncReport:
    flags: list[SyncFlag] = field(default_factory=list)

    def add(self, flag: SyncFlag):
        self.flags.append(flag)

    def by_type(self, flag_type: FlagType) -> list[SyncFlag]:
        return [f for f in self.flags if f.flag == flag_type]

    def summary(self) -> str:
        lines = []
        for flag_type in FlagType:
            items = self.by_type(flag_type)
            if not items:
                lines.append(f"\n[{flag_type.value}] (0) — aucune entrée")
                continue
            lines.append(f"\n[{flag_type.value}] ({len(items)})")
            for f in items:
                if flag_type == FlagType.MISPLACED:
                    lines.append(
                        f"  - {f.artist} — {f.title}\n"
                        f"    Deezer: '{f.deezer_playlist}'  RB: '{f.rb_tag}'"
                    )
                elif flag_type == FlagType.DOWNLOAD_NEEDED:
                    lines.append(
                        f"  - {f.artist} — {f.title}  (playlist: {f.deezer_playlist})"
                    )
                else:
                    lines.append(f"  - {f.artist} — {f.title}")
        return "\n".join(lines)


def _normalize_tag(s: str) -> str:
    return s.lower().replace("-", " ").replace("_", " ").strip()


def _is_soundcloud(track: dict) -> bool:
    return "soundcloud" in [t.lower() for t in (track.get("tags") or [])]


def _match_rb_tag(deezer_playlist: str, rb_tag_names: list[str]) -> str | None:
    """Trouve le tag RB correspondant à une playlist Deezer (strip préfixe + fuzzy)."""
    from difflib import get_close_matches

    candidate = deezer_playlist.removeprefix("W - ")
    norm = _normalize_tag(candidate)
    for tag in rb_tag_names:
        if _normalize_tag(tag) == norm:
            return tag
    matches = get_close_matches(
        norm, [_normalize_tag(t) for t in rb_tag_names], n=1, cutoff=0.85
    )
    if matches:
        for tag in rb_tag_names:
            if _normalize_tag(tag) == matches[0]:
                return tag
    return None


def check_sync(
    deezer_playlists: dict[str, list[dict]],
    rb_by_tag: dict[str, list[dict]],
) -> SyncReport:
    """
    Compare les playlists Deezer (W - ...) avec les tags Rekordbox.

    deezer_playlists : {playlist_title: [deezer_track, ...]}
        deezer_track = {"title": str, "artist": {"name": str}, ...}

    rb_by_tag : {tag_name: [rb_track, ...]}
        rb_track = {"title": str, "artist": str, "tags": [...], ...}
    """
    report = SyncReport()
    rb_tag_names = list(rb_by_tag.keys())

    # Index global RB : titre normalisé → {tag: track}
    rb_global: dict[str, dict[str, dict]] = {}
    for tag, tracks in rb_by_tag.items():
        for t in tracks:
            if _is_soundcloud(t):
                continue
            key = _normalize(t["title"])
            if key not in rb_global:
                rb_global[key] = {}
            rb_global[key][tag] = t

    # Index global Deezer : titre normalisé → {playlist: track}
    dz_global: dict[str, dict[str, dict]] = {}
    for pl_name, tracks in deezer_playlists.items():
        for t in tracks:
            key = _normalize(t["title"])
            if key not in dz_global:
                dz_global[key] = {}
            dz_global[key][pl_name] = t

    already_misplaced: set[str] = set()

    for pl_name, dz_tracks in deezer_playlists.items():
        rb_tag = _match_rb_tag(pl_name, rb_tag_names)
        rb_tracks_raw = rb_by_tag.get(rb_tag, []) if rb_tag else []

        # Déduplique RB par titre normalisé (garde le mieux noté)
        rb_keys: dict[str, dict] = {}
        for t in sorted(rb_tracks_raw, key=lambda x: x["rating"], reverse=True):
            if _is_soundcloud(t):
                continue
            k = _normalize(t["title"])
            if k not in rb_keys:
                rb_keys[k] = t

        dz_keys = {_normalize(t["title"]): t for t in dz_tracks}

        only_deezer = set(dz_keys) - set(rb_keys)
        only_rb = set(rb_keys) - set(dz_keys)

        for key in only_deezer:
            if key in already_misplaced:
                continue
            t = dz_keys[key]
            artist = t["artist"]["name"]
            if key in rb_global:
                wrong_rb_tags = list(rb_global[key].keys())
                report.add(
                    SyncFlag(
                        flag=FlagType.MISPLACED,
                        title=t["title"],
                        artist=artist,
                        deezer_playlist=pl_name,
                        rb_tag=wrong_rb_tags[0],
                        expected_rb_tag=rb_tag,
                    )
                )
                already_misplaced.add(key)
            else:
                report.add(
                    SyncFlag(
                        flag=FlagType.DOWNLOAD_NEEDED,
                        title=t["title"],
                        artist=artist,
                        deezer_playlist=pl_name,
                    )
                )

        for key in only_rb:
            if key in already_misplaced:
                continue
            t = rb_keys[key]
            artist = t["artist"] or "?"
            if key in dz_global:
                wrong_dz_playlists = list(dz_global[key].keys())
                report.add(
                    SyncFlag(
                        flag=FlagType.MISPLACED,
                        title=t["title"],
                        artist=artist,
                        deezer_playlist=wrong_dz_playlists[0],
                        rb_tag=rb_tag,
                        expected_deezer_playlist=pl_name,
                    )
                )
                already_misplaced.add(key)
            else:
                report.add(
                    SyncFlag(
                        flag=FlagType.ANOMALY,
                        title=t["title"],
                        artist=artist,
                        rb_tag=rb_tag,
                    )
                )

    return report
