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


def import_all():
    db = Rekordbox6Database()
    all_tracks = list(db.get_content())
    print(f"{len(all_tracks)} tracks dans Rekordbox.")

    resp = requests.get(f"{API_URL}/tracks/existing-ids")
    resp.raise_for_status()
    existing = {t["id"]: t["has_artwork"] for t in resp.json()}
    print(f"{len(existing)} tracks déjà en base.")

    BATCH_SIZE = 100
    batch = []
    total_inserted = total_updated = total_artworks = 0

    for i, t in enumerate(all_tracks):
        already_has_artwork = existing.get(t.ID, False)
        image_path = resolve_image(t.ImagePath) if not already_has_artwork else None

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
                "image_base64": encode_image(image_path),
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
