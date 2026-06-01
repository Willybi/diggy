"""
Script d'import Rekordbox → API Diggy.
A lancer depuis le PC qui a accès à la base Rekordbox.

Usage:
    python import_rekordbox.py
"""
import base64
import json
import os
import requests
from pyrekordbox import Rekordbox6Database

API_URL = os.environ.get("DIGGY_API_URL", "http://82.29.168.247/api")
BATCH_SIZE = 100  # nombre de tracks envoyés par requête


def encode_image(path: str) -> str | None:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def main():
    print("Connexion à Rekordbox...")
    db = Rekordbox6Database()

    print("Récupération des tracks existants depuis l'API...")
    resp = requests.get(f"{API_URL}/tracks/existing-ids")
    resp.raise_for_status()
    existing = {t["id"]: t["has_artwork"] for t in resp.json()}
    print(f"  {len(existing)} tracks déjà en base.")

    all_tracks = list(db.get_content())
    print(f"  {len(all_tracks)} tracks dans Rekordbox.")

    batch = []
    total_inserted = 0
    total_updated = 0
    total_artworks = 0

    for i, t in enumerate(all_tracks):
        already_has_artwork = existing.get(t.ID, {}) and existing.get(t.ID) is True

        # Image : uniquement si pas déjà uploadée
        image_base64 = None
        if not already_has_artwork:
            image_base64 = encode_image(t.ImagePath)

        batch.append({
            "id": t.ID,
            "title": t.Title,
            "artist": t.ArtistName,
            "bpm": float(t.BPM) if t.BPM else None,
            "key": str(t.Key) if t.Key else None,
            "duration": t.Duration,
            "rating": t.Rating,
            "file_path": t.FolderPath,
            "date_added": t.DateAdded.isoformat() if t.DateAdded else None,
            "tags": list(t.MyTagNames or []),
            "image_base64": image_base64,
        })

        if len(batch) >= BATCH_SIZE or i == len(all_tracks) - 1:
            resp = requests.post(f"{API_URL}/tracks/bulk", json=batch)
            resp.raise_for_status()
            result = resp.json()
            total_inserted += result["inserted"]
            total_updated += result["updated"]
            total_artworks += result["artworks_uploaded"]
            print(f"  Batch {i // BATCH_SIZE + 1} : +{result['inserted']} insérés, ~{result['updated']} mis à jour, {result['artworks_uploaded']} images")
            batch = []

    print(f"\nImport terminé : {total_inserted} insérés, {total_updated} mis à jour, {total_artworks} images uploadées.")


if __name__ == "__main__":
    main()
