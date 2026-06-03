"""Faux objets imitant les réponses de l'API Deezer pour les tests."""

PLAYLISTS_PAGE_1 = {
    "data": [
        {"id": "111", "title": "W - Tech House", "nb_tracks": 2, "creator": {"name": "willi"}},
        {"id": "222", "title": "W - Melodic", "nb_tracks": 1, "creator": {"name": "willi"}},
        {"id": "333", "title": "Favorites", "nb_tracks": 5, "creator": {"name": "willi"}},
    ],
    "next": None,
}

PLAYLISTS_PAGE_2 = {
    "data": [
        {"id": "444", "title": "W - Deep", "nb_tracks": 3, "creator": {"name": "willi"}},
    ],
    "next": None,
}

PLAYLISTS_PAGINATED = {
    "data": [
        {"id": "111", "title": "W - Tech House", "nb_tracks": 2, "creator": {"name": "willi"}},
    ],
    "next": "https://api.deezer.com/user/123/playlists?limit=50&index=50",
}

TRACKS_PAGE_1 = {
    "data": [
        {"id": "t1", "title": "Wannabe", "artist": {"name": "VOLAC"}, "duration": 185},
        {"id": "t2", "title": "Losing It", "artist": {"name": "Fisher"}, "duration": 370},
    ],
    "next": None,
}

TRACKS_PAGINATED = {
    "data": [
        {"id": "t1", "title": "Wannabe", "artist": {"name": "VOLAC"}, "duration": 185},
    ],
    "next": "https://api.deezer.com/playlist/111/tracks?limit=100&index=100",
}

TRACKS_PAGE_2 = {
    "data": [
        {"id": "t2", "title": "Losing It", "artist": {"name": "Fisher"}, "duration": 370},
    ],
    "next": None,
}
