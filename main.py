import base64
import os

import requests
from pyrekordbox import Rekordbox6Database

API_URL = os.environ.get("DIGGY_API_URL", "http://82.29.168.247/api")
RB_ARTWORK_ROOT = os.environ.get(
    "RB_ARTWORK_ROOT", r"C:\Users\willi\AppData\Roaming\Pioneer\rekordbox\share"
)


def resolve_image(image_path: str) -> str | None:
    if not image_path:
        return None
    full = os.path.join(RB_ARTWORK_ROOT, image_path.lstrip("/").replace("/", os.sep))
    return full if os.path.exists(full) else None


def encode_image(path: str) -> str | None:
    if not path:
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# test
def encode_image_from_audio(audio_path: str) -> str | None:
    """Extrait l'artwork depuis les tags ID3/MP4 du fichier audio."""
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


def import_all():
    db = Rekordbox6Database()
    all_tracks = [t for t in db.get_content() if t.rb_data_status == 256]
    print(f"{len(all_tracks)} tracks actifs dans Rekordbox.")

    resp = requests.get(f"{API_URL}/tracks/existing-ids")
    resp.raise_for_status()
    existing = {t["id"]: t["has_artwork"] for t in resp.json()}
    print(f"{len(existing)} tracks déjà en base.")

    BATCH_SIZE = 20
    batch = []
    total_inserted = total_updated = total_artworks = 0

    for i, t in enumerate(all_tracks):
        already_has_artwork = existing.get(t.ID, False)

        image_b64 = None
        if not already_has_artwork:
            rb_path = resolve_image(t.ImagePath)
            if rb_path:
                image_b64 = encode_image(rb_path)
            else:
                image_b64 = encode_image_from_audio(t.FolderPath)

        batch.append(
            {
                "id": t.ID,
                "title": t.Title,
                "artist": t.ArtistName,
                "bpm": round(float(t.BPM) / 100, 2) if t.BPM else None,
                "key": t.Key.ScaleName if t.Key else None,
                "duration": t.Length,
                "rating": t.Rating,
                "file_path": t.FolderPath,
                "date_added": str(t.DateCreated) if t.DateCreated else None,
                "tags": list(t.MyTagNames or []),
                "image_base64": image_b64,
            }
        )

        if len(batch) >= BATCH_SIZE or i == len(all_tracks) - 1:
            resp = requests.post(f"{API_URL}/tracks/bulk", json=batch)
            resp.raise_for_status()
            result = resp.json()
            total_inserted += result["inserted"]
            total_updated += result["updated"]
            total_artworks += result["artworks_uploaded"]
            print(
                f"  Batch {i // BATCH_SIZE + 1} : +{result['inserted']} insérés, ~{result['updated']} mis à jour, {result['artworks_uploaded']} images"
            )
            batch = []

    print(
        f"\nImport terminé : {total_inserted} insérés, {total_updated} mis à jour, {total_artworks} images uploadées."
    )


if __name__ == "__main__":
    import_all()
