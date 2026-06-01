import base64
import os

import requests
from pyrekordbox import Rekordbox6Database

API_URL = os.environ.get("DIGGY_API_URL", "http://82.29.168.247/api")


def encode_image(path: str) -> str | None:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def import_one():
    db = Rekordbox6Database()
    t = list(db.get_content())[0]

    print(f"Track : {t.Title} — {t.ArtistName}")
    print(f"  BPM     : {t.BPM}")
    print(f"  Tags    : {t.MyTagNames}")
    print(f"  Image   : {t.ImagePath}")

    payload = [
        {
            "id": t.ID,
            "title": t.Title,
            "artist": t.ArtistName,
            "bpm": round(float(t.BPM) / 100, 2) if t.BPM else None,
            "key": t.Key.Name if t.Key else None,
            "duration": t.Length,
            "rating": t.Rating,
            "file_path": t.FolderPath,
            "date_added": str(t.DateCreated) if t.DateCreated else None,
            "tags": list(t.MyTagNames or []),
            "image_base64": encode_image(t.ImagePath),
        }
    ]

    print("\nEnvoi vers l'API...")
    resp = requests.post(f"{API_URL}/tracks/bulk", json=payload)
    resp.raise_for_status()
    print(f"Résultat : {resp.json()}")


if __name__ == "__main__":
    import_one()
