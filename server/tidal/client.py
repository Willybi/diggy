"""
Client Tidal API (OAuth2 Client Credentials).
Utilisé pour récupérer les métadonnées et tracks d'une playlist Tidal.
"""
import os
import time
import requests

TIDAL_AUTH_URL = "https://auth.tidal.com/v1/oauth2/token"
TIDAL_API_URL = "https://openapi.tidal.com/v2"
TIDAL_COUNTRY = "US"  # country code requis pour l'API


class TidalClient:
    def __init__(self):
        self.client_id = os.environ.get("TIDAL_CLIENT_ID", "")
        self.client_secret = os.environ.get("TIDAL_CLIENT_SECRET", "")
        self._token: str | None = None
        self._token_expires: float = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires - 30:
            return self._token
        resp = requests.post(
            TIDAL_AUTH_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/vnd.api+json",
        }

    def get_playlist_meta(self, playlist_id: str) -> dict:
        """
        Retourne title, track_count, owner d'une playlist Tidal.
        playlist_id : UUID (ex: 55b2c563-a238-4ebf-9a45-284fd5fbfa53)
        """
        url = f"{TIDAL_API_URL}/playlists/{playlist_id}"
        resp = requests.get(url, headers=self._headers(), params={"countryCode": TIDAL_COUNTRY}, timeout=10)
        if resp.status_code != 200:
            return {}
        data = resp.json().get("data", {})
        attrs = data.get("attributes", {})
        # owner via relationships -> owners
        owner = None
        try:
            included = resp.json().get("included", [])
            for item in included:
                if item.get("type") == "users":
                    owner = item.get("attributes", {}).get("username") or item.get("attributes", {}).get("name")
                    break
        except Exception:
            pass
        return {
            "title": attrs.get("name"),
            "track_count": attrs.get("numberOfItems"),
            "owner": owner,
            "cover_url": _extract_cover(attrs),
            "description": attrs.get("description"),
        }

    def get_playlist_tracks(self, playlist_id: str) -> list[dict]:
        """
        Retourne tous les tracks d'une playlist Tidal (paginé).
        Chaque track dict : {id, title, artist, isrc, duration_ms}
        """
        tracks = []
        cursor = None
        while True:
            params = {"countryCode": TIDAL_COUNTRY, "include": "items", "page[size]": 100}
            if cursor:
                params["page[cursor]"] = cursor
            url = f"{TIDAL_API_URL}/playlists/{playlist_id}/relationships/items"
            resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
            if resp.status_code != 200:
                break
            body = resp.json()
            # IDs des items dans data
            item_ids = [d["id"] for d in body.get("data", [])]
            # Tracks enrichis dans included
            included_map = {}
            for inc in body.get("included", []):
                if inc.get("type") in ("tracks",):
                    included_map[inc["id"]] = inc
            for tid in item_ids:
                inc = included_map.get(tid)
                if not inc:
                    tracks.append({"id": tid, "title": "", "artist": None, "isrc": None, "duration_ms": None})
                    continue
                attrs = inc.get("attributes", {})
                artist = None
                try:
                    for rel in inc.get("relationships", {}).get("artists", {}).get("data", []):
                        # Chercher dans included
                        for a in body.get("included", []):
                            if a.get("type") == "artists" and a.get("id") == rel.get("id"):
                                artist = a.get("attributes", {}).get("name")
                                break
                        if artist:
                            break
                except Exception:
                    pass
                tracks.append({
                    "id": tid,
                    "title": attrs.get("title", ""),
                    "artist": artist,
                    "isrc": attrs.get("isrc"),
                    "duration_ms": int(attrs.get("duration", 0)) * 1000 if attrs.get("duration") else None,
                })
            # Pagination
            next_cursor = body.get("meta", {}).get("cursor") or \
                          (body.get("links", {}) or {}).get("next")
            if not next_cursor or not item_ids:
                break
            cursor = next_cursor
        return tracks

    def get_cover_url(self, playlist_id: str) -> str | None:
        """Retourne l'URL de couverture d'une playlist Tidal."""
        meta = self.get_playlist_meta(playlist_id)
        return meta.get("cover_url")


def _extract_cover(attrs: dict) -> str | None:
    """Extrait l'URL de cover depuis les attributs d'une playlist/track Tidal."""
    images = attrs.get("imageCover") or attrs.get("imageLinks") or []
    if isinstance(images, list) and images:
        # Prend la plus grande
        best = max(images, key=lambda x: x.get("width", 0) if isinstance(x, dict) else 0)
        return best.get("href") if isinstance(best, dict) else None
    return None
