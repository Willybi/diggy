import base64
import os
from collections import defaultdict

from pyrekordbox import Rekordbox6Database

# Canonical style names (used in DB and frontend)
KNOWN_STYLES = {
    'Downtempo', 'Nu Disco', 'Deep House', 'UK House',
    'French Touch', 'Tech House', 'UK Garage',
    'Electro brut', 'Melodic Techno', 'Classic/Min. Techno', 'Hard/Dark Techno',
    'Psytrance', 'Trance Techno',
    'Misc. Tracks',
}

# RB tag name → canonical name (handles case/format variants)
STYLE_ALIASES = {
    'Nu-Disco':    'Nu Disco',
    'Electro Brut': 'Electro brut',
}


class RekordboxExtractor:
    def __init__(self, artwork_root: str = None):
        self.db = Rekordbox6Database()
        self.artwork_root = artwork_root or os.environ.get(
            "RB_ARTWORK_ROOT",
            r"C:\Users\willi\AppData\Roaming\Pioneer\rekordbox\share",
        )

    def get_tracks(self) -> list:
        return [
            t for t in self.db.get_content()
            if t.rb_data_status == 256
            and (t.ArtistName or "").strip().lower() != "rekordbox"
        ]

    def get_track_metadata(self, track) -> dict:
        return {
            "id": track.ID,
            "title": track.Title,
            "artist": track.ArtistName,
            "bpm": round(float(track.BPM) / 100, 2) if track.BPM else None,
            "key": track.Key.ScaleName if track.Key else None,
            "duration": track.Length,
            "rating": track.Rating,
            "file_path": track.FolderPath,
            "date_added": str(track.DateCreated) if track.DateCreated else None,
            "tags": [STYLE_ALIASES.get(t, t) for t in (track.MyTagNames or []) if STYLE_ALIASES.get(t, t) in KNOWN_STYLES],
        }

    def get_track_cues(self, track_id: int) -> list:
        cues = [c for c in self.db.get_cue() if c.ContentID == track_id]
        result = []
        for c in sorted(cues, key=lambda x: x.InMsec):
            label = "MEM" if c.Kind == 0 else chr(ord("A") + c.Kind - 1)
            result.append(
                {
                    "label": label,
                    "kind": c.Kind,
                    "position_ms": c.InMsec,
                    "color": c.Color,
                    "is_loop": bool(c.ActiveLoop),
                }
            )
        return result

    def get_tags_structure(self) -> dict:
        tags = list(self.db.get_my_tag())
        tag_songs = list(self.db.get_my_tag_songs())
        used_tags = {s.MyTag.Name for s in tag_songs}
        groups = {t.ID: t.Name for t in tags if t.Attribute == 1}
        result = {name: [] for name in groups.values()}
        for tag in tags:
            if tag.Attribute == 0 and tag.ParentID in groups and tag.Name in used_tags:
                result[groups[tag.ParentID]].append(tag.Name)
        return {k: v for k, v in result.items() if v}

    def get_tracks_by_tag(self, tag_name: str) -> list:
        tag_songs = list(self.db.get_my_tag_songs())
        by_tag = defaultdict(list)
        for s in tag_songs:
            by_tag[s.MyTag.Name].append(s.Content)
        return by_tag.get(tag_name, [])

    def get_artwork_b64(self, track) -> str | None:
        if track.ImagePath:
            full = os.path.join(
                self.artwork_root,
                track.ImagePath.lstrip("/").replace("/", os.sep),
            )
            if os.path.exists(full):
                with open(full, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
        return self._get_artwork_from_audio(track.FolderPath)

    def _get_artwork_from_audio(self, audio_path: str) -> str | None:
        if not audio_path or not os.path.exists(audio_path):
            return None
        try:
            ext = os.path.splitext(audio_path)[1].lower()
            if ext in (".mp3", ".flac", ".aiff", ".wav"):
                from mutagen.id3 import ID3

                tags = ID3(audio_path)
                apic = tags.get("APIC:")
                if apic:
                    return base64.b64encode(apic.data).decode("utf-8")
            elif ext in (".m4a", ".mp4", ".aac"):
                from mutagen.mp4 import MP4

                tags = MP4(audio_path)
                covr = tags.get("covr")
                if covr:
                    return base64.b64encode(bytes(covr[0])).decode("utf-8")
        except Exception:
            pass
        return None
