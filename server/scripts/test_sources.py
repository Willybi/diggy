"""
Feasibility test script for TIDAL and Spotify playlist sources.
Run locally: python server/scripts/test_sources.py
"""

import json
import sys
from pathlib import Path

SEPARATOR = "=" * 60


# ──────────────────────────────────────────────────────────────
# SPOTIFY (spotifyscraper)
# ──────────────────────────────────────────────────────────────


def test_spotify():
    print(f"\n{SEPARATOR}")
    print("SPOTIFY — spotifyscraper feasibility test")
    print(SEPARATOR)

    try:
        from spotify_scraper import SpotifyClient
    except ImportError:
        print("[FAIL] spotifyscraper not installed. Run: pip install spotifyscraper")
        return False

    # Public playlist: Today's Top Hits
    playlist_url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"

    print(f"\nFetching playlist: {playlist_url}")
    print("(max_tracks=15 for quick test)\n")

    try:
        client = SpotifyClient()
        playlist = client.get_playlist(playlist_url, max_tracks=15)
    except Exception as e:
        print(f"[FAIL] Could not fetch playlist: {e}")
        return False

    # Playlist metadata
    print(f"  Playlist name   : {playlist.name}")
    print(f"  Owner           : {playlist.owner.name if playlist.owner else 'N/A'}")
    print(f"  Total tracks    : {playlist.total_tracks}")
    print(f"  Fetched tracks  : {len(playlist.tracks)}")
    print(f"  Description     : {(playlist.description or '')[:80]}")
    print(f"  Images          : {len(playlist.images)}")
    if playlist.images:
        print(f"  First image URL : {playlist.images[0].url}")

    # Track details
    print(f"\n{'#':<4} {'Title':<40} {'Artist':<25} {'Dur(ms)':<10} {'Preview?'}")
    print("-" * 90)

    has_preview = 0
    for i, pt in enumerate(playlist.tracks):
        t = pt.track
        artist_name = t.artists[0].name if t.artists else "?"
        has_prev = "Yes" if t.preview_url else "No"
        if t.preview_url:
            has_preview += 1
        title_short = t.name[:38] if len(t.name) > 38 else t.name
        artist_short = artist_name[:23] if len(artist_name) > 23 else artist_name
        print(
            f"{i + 1:<4} {title_short:<40} {artist_short:<25} {t.duration_ms:<10} {has_prev}"
        )

    total = len(playlist.tracks)
    print("\n--- Spotify Report ---")
    print(f"  Tracks fetched    : {total}")
    print("  ISRC available    : NO (not in spotifyscraper Track model)")
    print(
        f"  Preview URL       : {has_preview}/{total} ({100 * has_preview // total if total else 0}%)"
    )
    print("  Matching strategy : title + artist -> Deezer cross-search")
    print(f"  Status            : {'OK' if total > 0 else 'FAIL'}")

    client.close()
    return total > 0


# ──────────────────────────────────────────────────────────────
# TIDAL (tidalapi)
# ──────────────────────────────────────────────────────────────

TIDAL_TOKEN_FILE = Path(__file__).parent / ".tidal_tokens.json"


def test_tidal():
    print(f"\n{SEPARATOR}")
    print("TIDAL — tidalapi feasibility test")
    print(SEPARATOR)

    try:
        import tidalapi
    except ImportError:
        print("[FAIL] tidalapi not installed. Run: pip install tidalapi")
        return False

    session = tidalapi.Session()

    # Try loading saved tokens first
    if TIDAL_TOKEN_FILE.exists():
        print(f"Found saved tokens at {TIDAL_TOKEN_FILE}")
        tokens = json.loads(TIDAL_TOKEN_FILE.read_text())
        try:
            session.load_oauth_session(
                token_type=tokens["token_type"],
                access_token=tokens["access_token"],
                refresh_token=tokens.get("refresh_token"),
                expiry_time=tokens.get("expiry_time"),
            )
            if session.check_login():
                print("  Loaded saved session OK")
            else:
                print("  Saved session expired, re-authenticating...")
                session = tidalapi.Session()
                raise ValueError("expired")
        except Exception:
            print("  Saved tokens invalid, starting fresh OAuth...")
            session = tidalapi.Session()
            _tidal_oauth(session)
    else:
        _tidal_oauth(session)

    if not session.check_login():
        print("[FAIL] Could not authenticate with TIDAL")
        return False

    # Save tokens for reuse
    _save_tidal_tokens(session)

    # Fetch a public/editorial playlist
    # TIDAL Top 50 Global: a]uuid — try a well-known one
    # Use search instead to find a playlist
    print("\nSearching for 'Top 50 Global' playlists...")
    try:
        results = session.search(
            "Top 50 Global", models=[tidalapi.playlist.Playlist], limit=3
        )
        playlists = results.get("playlists", []) if isinstance(results, dict) else []
        if not playlists:
            # Try fetching user favorites or any editorial playlist
            print("  No search results. Trying editorial playlist...")
            # Known TIDAL editorial playlist UUIDs
            test_ids = [
                "1acda881-4556-4212-a384-1f1e4e85dd76",  # TIDAL Rising
            ]
            playlist = None
            for tid in test_ids:
                try:
                    playlist = session.playlist(tid)
                    break
                except Exception:
                    continue
            if not playlist:
                print("[FAIL] Could not find any test playlist")
                return False
        else:
            playlist = playlists[0]
    except Exception as e:
        print(f"[FAIL] Search error: {e}")
        return False

    print(f"\n  Playlist name  : {playlist.name}")
    print(f"  Num tracks     : {playlist.num_tracks}")
    print(f"  Creator        : {getattr(playlist, 'creator', 'N/A')}")
    print(f"  Description    : {(playlist.description or '')[:80]}")
    print(f"  Last updated   : {getattr(playlist, 'last_updated', 'N/A')}")

    # Fetch tracks (limit to 15)
    print("\nFetching tracks (limit 15)...")
    try:
        tracks = playlist.tracks(limit=15)
    except Exception as e:
        print(f"[FAIL] Could not fetch tracks: {e}")
        return False

    print(
        f"\n{'#':<4} {'Title':<35} {'Artist':<25} {'ISRC':<16} {'Dur(s)':<8} {'Quality'}"
    )
    print("-" * 100)

    has_isrc = 0
    for i, t in enumerate(tracks):
        artist_name = t.artist.name if t.artist else "?"
        isrc = getattr(t, "isrc", None) or ""
        if isrc:
            has_isrc += 1
        quality = getattr(t, "audio_quality", "?")
        title_short = t.name[:33] if len(t.name) > 33 else t.name
        artist_short = artist_name[:23] if len(artist_name) > 23 else artist_name
        print(
            f"{i + 1:<4} {title_short:<35} {artist_short:<25} {isrc:<16} {t.duration:<8} {quality}"
        )

    total = len(tracks)
    print("\n--- TIDAL Report ---")
    print(f"  Tracks fetched    : {total}")
    print(
        f"  ISRC available    : {has_isrc}/{total} ({100 * has_isrc // total if total else 0}%)"
    )
    print("  Matching strategy : ISRC (primary) + title+artist fallback via Deezer")
    print(
        f"  Auth type         : OAuth device flow (tokens saved to {TIDAL_TOKEN_FILE})"
    )
    print(f"  Status            : {'OK' if total > 0 else 'FAIL'}")

    return total > 0


def _tidal_oauth(session):
    """Run TIDAL OAuth device authorization flow."""
    print("\nStarting TIDAL OAuth device authorization...")
    print("You will need to open a URL in your browser and log in.\n")

    login, future = session.login_oauth()
    print(f"  1. Open this URL: {login.verification_uri_complete}")
    print("  2. Log in with your TIDAL account")
    print(f"  3. Waiting for authorization (expires in {login.expires_in}s)...\n")

    try:
        future.result(timeout=login.expires_in)
        print("  Authorization successful!")
    except Exception as e:
        print(f"  Authorization failed: {e}")


def _save_tidal_tokens(session):
    """Save TIDAL session tokens for reuse."""
    tokens = {
        "token_type": session.token_type,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expiry_time": session.expiry_time,
    }
    TIDAL_TOKEN_FILE.write_text(json.dumps(tokens, indent=2, default=str))
    print(f"  Tokens saved to {TIDAL_TOKEN_FILE}")


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    run_spotify = not args or "spotify" in args
    run_tidal = not args or "tidal" in args

    results = {}

    if run_spotify:
        results["spotify"] = test_spotify()

    if run_tidal:
        results["tidal"] = test_tidal()

    print(f"\n{SEPARATOR}")
    print("SUMMARY")
    print(SEPARATOR)
    for source, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {source:<12} : {status}")

    if all(results.values()):
        print("\nAll tests passed — ready to implement!")
    elif results.get("spotify"):
        print("\nSpotify OK. TIDAL needs investigation (account/subscription?).")
    else:
        print("\nSome tests failed — review output above.")
