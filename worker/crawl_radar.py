"""
Crawl les playlists surveillées (watched_playlists) et insère les tracks détectés
dans radar_tracks via l'API.

Usage:
    python -m worker.crawl_radar
    python -m worker.crawl_radar --dry-run   # affiche sans insérer
"""
import argparse
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

API_BASE = os.environ.get("DIGGY_API_URL", "http://localhost:8000")
DEEZER_API = "https://api.deezer.com"


def fetch_watched_playlists() -> list[dict]:
    r = requests.get(f"{API_BASE}/api/watchlist/", timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_deezer_tracks(playlist_id: str) -> list[dict]:
    tracks = []
    url = f"{DEEZER_API}/playlist/{playlist_id}/tracks?limit=100&index=0"
    while url:
        resp = requests.get(url, timeout=10).json()
        tracks.extend(resp.get("data", []))
        url = resp.get("next")
    return tracks


def insert_radar_track(payload: dict) -> bool:
    r = requests.post(f"{API_BASE}/api/radar/", json=payload, timeout=10)
    return r.status_code == 201


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Affiche sans insérer")
    args = parser.parse_args()

    playlists = fetch_watched_playlists()
    if not playlists:
        print("Aucune playlist surveillée.")
        return

    print(f"{len(playlists)} playlist(s) surveillée(s).\n")

    total_inserted = 0
    total_skipped = 0

    for pl in playlists:
        if pl["source"] != "deezer":
            print(f"  [{pl['source']}] {pl['title'] or pl['external_id']} — source non supportée, ignorée.")
            continue

        print(f"  [deezer] {pl['title'] or pl['external_id']} (id: {pl['external_id']})")
        try:
            tracks = fetch_deezer_tracks(pl["external_id"])
        except Exception as e:
            print(f"    Erreur fetch: {e}")
            continue

        print(f"    {len(tracks)} tracks trouvés.")

        for t in tracks:
            isrc = t.get("isrc") or None
            artist = t.get("artist", {}).get("name") if isinstance(t.get("artist"), dict) else None
            payload = {
                "watched_playlist_id": pl["id"],
                "external_track_id": str(t["id"]),
                "source": "deezer",
                "title": t.get("title", ""),
                "artist": artist,
                "isrc": isrc,
            }

            if args.dry_run:
                print(f"    [dry-run] {artist} — {t.get('title')}  (isrc: {isrc})")
                total_inserted += 1
            else:
                if insert_radar_track(payload):
                    total_inserted += 1
                else:
                    total_skipped += 1

    print()
    if args.dry_run:
        print(f"[dry-run] {total_inserted} tracks seraient insérés.")
    else:
        print(f"Insérés : {total_inserted}  |  Erreurs : {total_skipped}")


if __name__ == "__main__":
    main()
