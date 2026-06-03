import requests


class DeezerExtractor:
    BASE_URL = "https://api.deezer.com"

    def __init__(self, user_id: str):
        self.user_id = user_id

    def get_playlists(self, prefix: str = "W -") -> list[dict]:
        """Retourne toutes les playlists publiques dont le titre commence par `prefix`."""
        playlists = []
        url = f"{self.BASE_URL}/user/{self.user_id}/playlists?limit=50&index=0"
        while url:
            resp = requests.get(url).json()
            playlists.extend(resp.get("data", []))
            url = resp.get("next")
        return [pl for pl in playlists if pl["title"].startswith(prefix)]

    def get_tracks(self, playlist_id: str) -> list[dict]:
        """Retourne tous les sons d'une playlist (gère la pagination)."""
        tracks = []
        url = f"{self.BASE_URL}/playlist/{playlist_id}/tracks?limit=100&index=0"
        while url:
            resp = requests.get(url).json()
            tracks.extend(resp.get("data", []))
            url = resp.get("next")
        return tracks

    def get_all_tracks(self) -> dict[str, list[dict]]:
        """Retourne un dict {playlist_title: [tracks]} pour toutes les playlists W -."""
        result = {}
        for pl in self.get_playlists():
            result[pl["title"]] = self.get_tracks(pl["id"])
        return result
