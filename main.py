import argparse
import os
import sys

import requests

from worker.rekordbox.extractor import RekordboxExtractor

API_URL = os.environ.get("DIGGY_API_URL", "http://82.29.168.247/api")
BATCH_SIZE = 20


def get_token(api_url: str, email: str, password: str) -> str:
    """Authenticate and return a JWT token."""
    resp = requests.post(
        f"{api_url}/auth/login",
        json={"email": email, "password": password},
    )
    if resp.status_code == 401:
        print("Erreur : identifiants invalides.", file=sys.stderr)
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()["token"]


def make_session(token: str) -> requests.Session:
    """Create a requests session with the Authorization header."""
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    return s


def import_all(api_url: str, session: requests.Session):
    extractor = RekordboxExtractor()
    tracks = extractor.get_tracks()
    print(f"{len(tracks)} tracks actifs dans Rekordbox.")

    resp = session.get(f"{api_url}/tracks/existing-ids")
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
            resp = session.post(f"{api_url}/tracks/bulk", json=batch)
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

    print(
        f"\nImport terminé : {total_inserted} insérés, {total_updated} mis à jour, {total_artworks} images uploadées."
    )


def main():
    parser = argparse.ArgumentParser(description="Import Rekordbox library into Diggy")
    parser.add_argument("--email", help="Account email for authentication")
    parser.add_argument("--password", help="Account password")
    parser.add_argument("--token", help="JWT token (alternative to email/password)")
    parser.add_argument("--api-url", default=API_URL, help=f"API base URL (default: {API_URL})")
    args = parser.parse_args()

    api_url = args.api_url

    if args.token:
        token = args.token
    elif args.email and args.password:
        token = get_token(api_url, args.email, args.password)
    else:
        print("Erreur : --email + --password ou --token requis.", file=sys.stderr)
        sys.exit(1)

    session = make_session(token)

    # Verify auth works
    me_resp = session.get(f"{api_url}/auth/me")
    if me_resp.status_code != 200:
        print("Erreur : token invalide ou expiré.", file=sys.stderr)
        sys.exit(1)
    user = me_resp.json()
    print(f"Connecté en tant que {user['username']} (id={user['id']})")

    import_all(api_url, session)


if __name__ == "__main__":
    main()
