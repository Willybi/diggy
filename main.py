import os

import requests

from worker.rekordbox.extractor import RekordboxExtractor

API_URL = os.environ.get("DIGGY_API_URL", "http://82.29.168.247/api")
BATCH_SIZE = 20


def import_all():
    extractor = RekordboxExtractor()
    tracks = extractor.get_tracks()
    print(f"{len(tracks)} tracks actifs dans Rekordbox.")

    resp = requests.get(f"{API_URL}/tracks/existing-ids")
    resp.raise_for_status()
    existing = {t["id"]: t["has_artwork"] for t in resp.json()}
    print(f"{len(existing)} tracks déjà en base.")

    batch = []
    total_inserted = total_updated = total_artworks = 0

    for i, t in enumerate(tracks):
        metadata = extractor.get_track_metadata(t)
        if not existing.get(t.ID, False):
            metadata["image_base64"] = extractor.get_artwork_b64(t)
        else:
            metadata["image_base64"] = None
        batch.append(metadata)

        if len(batch) >= BATCH_SIZE or i == len(tracks) - 1:
            resp = requests.post(f"{API_URL}/tracks/bulk", json=batch)
            resp.raise_for_status()
            result = resp.json()
            total_inserted += result["inserted"]
            total_updated += result["updated"]
            total_artworks += result["artworks_uploaded"]
            print(
                f"  Batch {i // BATCH_SIZE + 1} : +{result['inserted']} insérés, "
                f"~{result['updated']} mis à jour, {result['artworks_uploaded']} images"
            )
            batch = []

    print(f"\nImport terminé : {total_inserted} insérés, {total_updated} mis à jour, {total_artworks} images uploadées.")


if __name__ == "__main__":
    import_all()
