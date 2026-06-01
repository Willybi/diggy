import base64
import os

import requests
from pyrekordbox import Rekordbox6Database

API_URL = os.environ.get("DIGGY_API_URL", "http://82.29.168.247/api")
RB_ARTWORK_ROOT = os.environ.get(
    "RB_ARTWORK_ROOT",
    r"C:\Users\willi\AppData\Roaming\Pioneer\rekordbox\share"
)


def encode_image(path: str) -> str | None:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def import_one():
    db = Rekordbox6Database()
    all_tracks = list(db.get_content())
    # Prendre le premier track qui a une image existante
    t = next(
        (t for t in all_tracks if t.ImagePath and os.path.exists(
            os.path.join(RB_ARTWORK_ROOT, t.ImagePath.lstrip("/").replace("/", os.sep))
        )),
        all_tracks[0]
    )

    print(f"Track : {t.Title} — {t.ArtistName}")
    print(f"  BPM     : {t.BPM}")
    print(f"  Tags    : {t.MyTagNames}")
    resolved = os.path.join(RB_ARTWORK_ROOT, t.ImagePath.lstrip("/").replace("/", os.sep)) if t.ImagePath else None
    print(f"  Image   : {t.ImagePath}")
    print(f"  Resolved: {resolved} — exists: {os.path.exists(resolved) if resolved else False}")

    payload = [
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
            "image_base64": encode_image(
                os.path.join(RB_ARTWORK_ROOT, t.ImagePath.lstrip("/").replace("/", os.sep))
                if t.ImagePath else None
            ),
        }
    ]

    print("\nEnvoi vers l'API...")
    resp = requests.post(f"{API_URL}/tracks/bulk", json=payload)
    resp.raise_for_status()
    print(f"Résultat : {resp.json()}")


if __name__ == "__main__":
    import_one()
