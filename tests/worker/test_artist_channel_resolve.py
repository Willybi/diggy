"""Tests for the artist→YouTube-channel resolver (workers/artist_channel_resolve,
C14.b 🅱 L1).

Same conventions as test_youtube.py:

  * PURE guards (``is_topic_channel`` / ``fold_match`` / ``is_music_entity`` /
    ``parse_youtube_ref``) — exercised directly, no network.
  * The network cores (``resolve_wikidata`` / ``resolve_musicbrainz``) and the full
    ``resolve_artist_channel`` cascade — driven with a tiny in-process fake ``httpx``
    client and a no-op async ``sleep`` (zero real network, zero wall time).

No fixtures are refactored; the ``server`` root is put on sys.path the same way as
test_youtube.py so ``workers.*`` imports resolve.
"""
import asyncio
import os
import sys

# Make the workers package importable (same pattern as test_youtube.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

import pytest  # noqa: E402
from workers.artist_channel_resolve import (  # noqa: E402
    ChannelResolveHTTPError,
    fold_match,
    is_music_entity,
    is_topic_channel,
    parse_youtube_ref,
    resolve_artist_channel,
    resolve_musicbrainz,
    resolve_wikidata,
    youtube_url_from_ref,
)

_UC = "UCabcdefghijklmnopqrstuv"  # UC + 22 chars


async def _nosleep(_delay):
    """No-op async sleep injected in place of asyncio.sleep (no wall time)."""
    return None


# ── Fake httpx client ─────────────────────────────────────────────────────────


class _FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeClient:
    """Minimal async stand-in for httpx.AsyncClient.get, capturing calls.

    ``handler(url, params)`` returns a :class:`_FakeResp`; a handler that RAISES
    exercises the transport-error isolation branch.
    """

    def __init__(self, handler):
        self._handler = handler
        self.calls = []

    async def get(self, url, params=None, headers=None):
        self.calls.append((url, params or {}, headers or {}))
        return self._handler(url, params or {})


def _never(url, params):  # a client that must NOT be called
    raise AssertionError(f"unexpected request to {url}")


# ── Wikidata claim builders ───────────────────────────────────────────────────


def _entity_claim(qid):
    return {"mainsnak": {"datavalue": {"value": {"entity-type": "item", "id": qid}}}}


def _string_claim(value):
    return {"mainsnak": {"datavalue": {"value": value}}}


def _wiki_handler(claims, *, qid="Q123", search_hits=None):
    """A Wikidata fake: wbsearchentities → ``qid``, wbgetentities → ``claims``."""

    def handler(url, params):
        action = params.get("action")
        if action == "wbsearchentities":
            hits = search_hits if search_hits is not None else [{"id": qid}]
            return _FakeResp(200, {"search": hits})
        if action == "wbgetentities":
            return _FakeResp(200, {"entities": {qid: {"claims": claims}}})
        return _FakeResp(500)

    return handler


# ── Pure: is_topic_channel ────────────────────────────────────────────────────


class TestIsTopicChannel:
    @pytest.mark.parametrize(
        "title", ["Peggy Gou - Topic", "Amelie Lens - Topic", "foo - topic"]
    )
    def test_topic_excluded(self, title):
        assert is_topic_channel(title) is True

    @pytest.mark.parametrize(
        "title", ["Boiler Room", "Topics Channel", "Topic Music", "", None]
    )
    def test_non_topic(self, title):
        assert is_topic_channel(title) is False


# ── Pure: fold_match ──────────────────────────────────────────────────────────


class TestFoldMatch:
    def test_exact(self):
        assert fold_match("Peggy Gou", "Peggy Gou") is True

    def test_space_insensitive(self):
        assert fold_match("Amelie Lens", "AmelieLens") is True
        assert fold_match("David Guetta", "davidguettaofficial") is True

    def test_inclusion(self):
        assert fold_match("Boiler Room", "Boiler Room Official") is True

    def test_short_fold_rejected(self):
        # A 2-char fold ("ki") must not trivially match a long title.
        assert fold_match("KI", "Some Long Channel Name") is False

    def test_non_latin_never_matches(self):
        # A fully non-Latin name folds to "" → no signal.
        assert fold_match("にお", "Some Channel") is False

    def test_unrelated(self):
        assert fold_match("Peggy Gou", "Boiler Room") is False


# ── Pure: parse_youtube_ref + youtube_url_from_ref ────────────────────────────


class TestParseYoutubeRef:
    def test_channel(self):
        assert parse_youtube_ref(f"https://youtube.com/channel/{_UC}") == (
            "channel_id",
            _UC,
        )

    def test_handle(self):
        assert parse_youtube_ref("https://www.youtube.com/@boilerroom") == (
            "handle",
            "@boilerroom",
        )

    def test_custom_and_user(self):
        assert parse_youtube_ref("https://youtube.com/c/BoilerRoom") == (
            "custom",
            "BoilerRoom",
        )
        assert parse_youtube_ref("https://youtube.com/user/BoilerRoomTV") == (
            "user",
            "BoilerRoomTV",
        )

    def test_none(self):
        assert parse_youtube_ref("https://soundcloud.com/x") is None
        assert parse_youtube_ref(None) is None

    def test_url_from_ref(self):
        assert youtube_url_from_ref("channel_id", _UC).endswith(f"/channel/{_UC}")
        assert youtube_url_from_ref("handle", "@x") == "https://www.youtube.com/@x"


# ── Pure: is_music_entity (the entity guard) ──────────────────────────────────


class TestIsMusicEntity:
    def test_human_instance(self):
        assert is_music_entity({"P31": [_entity_claim("Q5")]}) is True

    def test_band_instance(self):
        assert is_music_entity({"P31": [_entity_claim("Q215380")]}) is True

    def test_occupation_dj(self):
        # Not a person-instance, but a DJ occupation → music entity.
        assert is_music_entity({"P106": [_entity_claim("Q130857")]}) is True

    def test_city_rejected(self):
        # A city (Q515) with no musical P106 → NOT a music entity.
        assert is_music_entity({"P31": [_entity_claim("Q515")]}) is False

    def test_empty(self):
        assert is_music_entity({}) is False


# ── resolve_wikidata: entity guard end-to-end ─────────────────────────────────


class TestResolveWikidata:
    def test_music_entity_with_channel_accepted(self):
        claims = {
            "P31": [_entity_claim("Q5")],
            "P2397": [_string_claim(_UC)],
            "P3040": [_string_claim("peggygou")],
        }
        client = _FakeClient(_wiki_handler(claims))
        got = asyncio.run(resolve_wikidata(client, "Peggy Gou", sleep=_nosleep))
        assert got["channel_id"] == _UC
        assert got["is_music_entity"] is True
        assert got["has_soundcloud"] is True

    def test_occupation_only_accepted(self):
        claims = {"P106": [_entity_claim("Q639669")], "P2397": [_string_claim(_UC)]}
        client = _FakeClient(_wiki_handler(claims))
        got = asyncio.run(resolve_wikidata(client, "Some Musician", sleep=_nosleep))
        assert got["channel_id"] == _UC
        assert got["is_music_entity"] is True

    def test_non_music_entity_with_channel_rejected(self):
        # A city carrying a stray P2397 → the guard rejects the channel.
        claims = {"P31": [_entity_claim("Q515")], "P2397": [_string_claim(_UC)]}
        client = _FakeClient(_wiki_handler(claims))
        got = asyncio.run(resolve_wikidata(client, "Barcelona", sleep=_nosleep))
        assert got["channel_id"] is None
        assert got["is_music_entity"] is False
        assert got["has_soundcloud"] is False

    def test_no_search_hit(self):
        client = _FakeClient(_wiki_handler({}, search_hits=[]))
        got = asyncio.run(resolve_wikidata(client, "Nobody", sleep=_nosleep))
        assert got["channel_id"] is None

    def test_blank_name_no_request(self):
        client = _FakeClient(_never)
        got = asyncio.run(resolve_wikidata(client, "  ", sleep=_nosleep))
        assert got["channel_id"] is None
        assert client.calls == []

    def test_http_error_raises(self):
        client = _FakeClient(lambda url, params: _FakeResp(503))
        with pytest.raises(ChannelResolveHTTPError):
            asyncio.run(resolve_wikidata(client, "X", sleep=_nosleep))


# ── resolve_musicbrainz ───────────────────────────────────────────────────────


def _mb_handler(*, mbid="mbid-1", relations=None, artists=None):
    def handler(url, params):
        if url.endswith("/artist"):  # search
            hits = artists if artists is not None else [{"id": mbid}]
            return _FakeResp(200, {"artists": hits})
        # /artist/<mbid>
        return _FakeResp(200, {"relations": relations or []})

    return handler


class TestResolveMusicbrainz:
    def test_channel_from_rels(self):
        relations = [
            {"url": {"resource": f"https://www.youtube.com/channel/{_UC}"}},
            {"url": {"resource": "https://soundcloud.com/peggygou"}},
        ]
        client = _FakeClient(_mb_handler(relations=relations))
        got = asyncio.run(resolve_musicbrainz(client, "Peggy Gou", sleep=_nosleep))
        assert got["channel_id"] == _UC
        assert got["channel_url"].endswith(f"/channel/{_UC}")
        assert got["has_soundcloud"] is True

    def test_provided_mbid_skips_search(self):
        relations = [{"url": {"resource": f"https://youtube.com/channel/{_UC}"}}]

        def handler(url, params):
            assert not url.endswith("/artist"), "search must be skipped"
            return _FakeResp(200, {"relations": relations})

        client = _FakeClient(handler)
        got = asyncio.run(
            resolve_musicbrainz(client, "X", mbid="mbid-9", sleep=_nosleep)
        )
        assert got["channel_id"] == _UC

    def test_no_youtube_rel(self):
        relations = [{"url": {"resource": "https://soundcloud.com/x"}}]
        client = _FakeClient(_mb_handler(relations=relations))
        got = asyncio.run(resolve_musicbrainz(client, "X", sleep=_nosleep))
        assert got["channel_id"] is None
        assert got["has_soundcloud"] is True

    def test_no_search_hit(self):
        client = _FakeClient(_mb_handler(artists=[]))
        got = asyncio.run(resolve_musicbrainz(client, "Nobody", sleep=_nosleep))
        assert got["channel_id"] is None


# ── resolve_artist_channel: the cascade ───────────────────────────────────────


def _yt_search_payload(hits):
    """A YouTube search.list payload from ``[(channel_id, title), …]``."""
    return {
        "items": [
            {
                "id": {"channelId": cid},
                "snippet": {
                    "title": title,
                    "description": "d",
                    "thumbnails": {"default": {"url": "u"}},
                },
            }
            for cid, title in hits
        ]
    }


class TestResolveArtistChannelCascade:
    def test_wikidata_wins_first(self):
        claims = {"P31": [_entity_claim("Q5")], "P2397": [_string_claim(_UC)]}
        wiki = _FakeClient(_wiki_handler(claims))
        got = asyncio.run(
            resolve_artist_channel(
                "Peggy Gou",
                wiki_client=wiki,
                mb_client=_FakeClient(_never),
                yt_client=_FakeClient(_never),
                api_key="k",
                sleep=_nosleep,
            )
        )
        assert got["method"] == "wikidata"
        assert got["confidence"] == "high"
        assert got["channel_id"] == _UC
        assert got["url"].endswith(f"/channel/{_UC}")

    def test_falls_through_to_musicbrainz(self):
        # Wikidata: non-music entity → no channel; MusicBrainz resolves.
        wiki_claims = {"P31": [_entity_claim("Q515")], "P2397": [_string_claim(_UC)]}
        wiki = _FakeClient(_wiki_handler(wiki_claims))
        mb = _FakeClient(
            _mb_handler(
                relations=[
                    {"url": {"resource": f"https://youtube.com/channel/{_UC}"}}
                ]
            )
        )
        got = asyncio.run(
            resolve_artist_channel(
                "X",
                wiki_client=wiki,
                mb_client=mb,
                yt_client=_FakeClient(_never),
                api_key="k",
                sleep=_nosleep,
            )
        )
        assert got["method"] == "musicbrainz"
        assert got["channel_id"] == _UC

    def test_falls_through_to_search(self):
        wiki = _FakeClient(_wiki_handler({}, search_hits=[]))
        mb = _FakeClient(_mb_handler(artists=[]))
        yt = _FakeClient(
            lambda url, params: _FakeResp(
                200, _yt_search_payload([(_UC, "Peggy Gou Official")])
            )
        )
        got = asyncio.run(
            resolve_artist_channel(
                "Peggy Gou",
                wiki_client=wiki,
                mb_client=mb,
                yt_client=yt,
                api_key="k",
                sleep=_nosleep,
            )
        )
        assert got["method"] == "search"
        assert got["confidence"] == "NEEDS_VERIFY"
        assert got["channel_id"] == _UC
        assert got["channel_title"] == "Peggy Gou Official"

    def test_search_skips_topic_then_takes_real(self):
        wiki = _FakeClient(_wiki_handler({}, search_hits=[]))
        mb = _FakeClient(_mb_handler(artists=[]))
        yt = _FakeClient(
            lambda url, params: _FakeResp(
                200,
                _yt_search_payload(
                    [("UCtopic0000000000000000", "Peggy Gou - Topic"),
                     (_UC, "Peggy Gou")]
                ),
            )
        )
        got = asyncio.run(
            resolve_artist_channel(
                "Peggy Gou",
                wiki_client=wiki,
                mb_client=mb,
                yt_client=yt,
                api_key="k",
                sleep=_nosleep,
            )
        )
        # The "- Topic" hit is excluded; the real channel is taken.
        assert got["channel_id"] == _UC

    def test_search_only_topic_hit_returns_none(self):
        wiki = _FakeClient(_wiki_handler({}, search_hits=[]))
        mb = _FakeClient(_mb_handler(artists=[]))
        yt = _FakeClient(
            lambda url, params: _FakeResp(
                200, _yt_search_payload([("UCtopic0000000000000000", "X - Topic")])
            )
        )
        got = asyncio.run(
            resolve_artist_channel(
                "X",
                wiki_client=wiki,
                mb_client=mb,
                yt_client=yt,
                api_key="k",
                sleep=_nosleep,
            )
        )
        assert got is None

    def test_search_hit_failing_fold_returns_none(self):
        wiki = _FakeClient(_wiki_handler({}, search_hits=[]))
        mb = _FakeClient(_mb_handler(artists=[]))
        yt = _FakeClient(
            lambda url, params: _FakeResp(
                200, _yt_search_payload([(_UC, "Completely Different Channel")])
            )
        )
        got = asyncio.run(
            resolve_artist_channel(
                "Peggy Gou",
                wiki_client=wiki,
                mb_client=mb,
                yt_client=yt,
                api_key="k",
                sleep=_nosleep,
            )
        )
        assert got is None

    def test_nothing_resolves_returns_none(self):
        wiki = _FakeClient(_wiki_handler({}, search_hits=[]))
        mb = _FakeClient(_mb_handler(artists=[]))
        got = asyncio.run(
            resolve_artist_channel(
                "Nobody",
                wiki_client=wiki,
                mb_client=mb,
                yt_client=_FakeClient(lambda url, params: _FakeResp(200, {})),
                api_key="k",
                sleep=_nosleep,
            )
        )
        assert got is None

    def test_no_api_key_skips_search(self):
        wiki = _FakeClient(_wiki_handler({}, search_hits=[]))
        mb = _FakeClient(_mb_handler(artists=[]))
        yt = _FakeClient(_never)  # must NOT be called without a key
        got = asyncio.run(
            resolve_artist_channel(
                "X",
                wiki_client=wiki,
                mb_client=mb,
                yt_client=yt,
                api_key="",
                sleep=_nosleep,
            )
        )
        assert got is None
        assert yt.calls == []

    def test_allow_search_false_skips_search(self):
        wiki = _FakeClient(_wiki_handler({}, search_hits=[]))
        mb = _FakeClient(_mb_handler(artists=[]))
        yt = _FakeClient(_never)
        got = asyncio.run(
            resolve_artist_channel(
                "X",
                wiki_client=wiki,
                mb_client=mb,
                yt_client=yt,
                api_key="k",
                allow_search=False,
                sleep=_nosleep,
            )
        )
        assert got is None
        assert yt.calls == []

    def test_wikidata_error_isolated_mb_resolves(self):
        # Wikidata transport error → isolated, MusicBrainz still resolves.
        wiki = _FakeClient(lambda url, params: _FakeResp(500))
        mb = _FakeClient(
            _mb_handler(
                relations=[
                    {"url": {"resource": f"https://youtube.com/channel/{_UC}"}}
                ]
            )
        )
        got = asyncio.run(
            resolve_artist_channel(
                "X",
                wiki_client=wiki,
                mb_client=mb,
                yt_client=_FakeClient(_never),
                api_key="k",
                sleep=_nosleep,
            )
        )
        assert got["method"] == "musicbrainz"

    def test_soundcloud_accumulates_across_tiers(self):
        # Wikidata notes SoundCloud but no channel; MusicBrainz gives the channel.
        wiki_claims = {
            "P31": [_entity_claim("Q5")],
            "P3040": [_string_claim("peggygou")],
        }  # music entity, SoundCloud, but NO P2397 channel
        wiki = _FakeClient(_wiki_handler(wiki_claims))
        mb = _FakeClient(
            _mb_handler(
                relations=[
                    {"url": {"resource": f"https://youtube.com/channel/{_UC}"}}
                ]
            )
        )
        got = asyncio.run(
            resolve_artist_channel(
                "Peggy Gou",
                wiki_client=wiki,
                mb_client=mb,
                yt_client=_FakeClient(_never),
                api_key="k",
                sleep=_nosleep,
            )
        )
        assert got["method"] == "musicbrainz"
        assert got["has_soundcloud"] is True

    def test_blank_name_returns_none(self):
        got = asyncio.run(
            resolve_artist_channel(
                "   ",
                wiki_client=_FakeClient(_never),
                mb_client=_FakeClient(_never),
                yt_client=_FakeClient(_never),
                api_key="k",
                sleep=_nosleep,
            )
        )
        assert got is None
