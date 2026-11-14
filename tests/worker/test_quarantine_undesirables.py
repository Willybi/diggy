"""Tests for the OPS masking script (scripts/quarantine_undesirables).

Exercises the testable core (``run_rule`` / ``revert_rule`` / ``read_tsv``) against a
real sync SQLite session (``sync_session`` fixture): dry-run writes nothing, the
farm_fort per-title protections (corroboration via set/library/opinion/collection,
anchored ISRC registrant, co-artist), the artist-level masking rule, the genre
guard, absent ids, idempotence, never overwriting another rule's reason, the
isrc_block rule, and a revert scoped to one rule.
"""
import io
import itertools
import os
import sys

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from models import (  # noqa: E402
    Album,
    Artist,
    ArtistCohort,
    CatalogAlbum,
    CatalogArtist,
    CatalogEntry,
    CollectionItem,
    DJSet,
    SetTrack,
    User,
    UserCollection,
    UserOpinion,
    UserTrack,
)
from scripts.quarantine_undesirables import (  # noqa: E402
    _print_report,
    has_classical_marker,
    has_episode_marker,
    is_episode_series_key,
    is_br_funk_registrant,
    is_junk,
    isrc_year,
    read_tsv,
    revert_rule,
    run_rule,
    series_key,
    top3_share,
)

_n = itertools.count(1)


def _artist(s, name="A", hidden=None):
    a = Artist(name=name, normalized_name=f"n-{next(_n)}-{name}", hidden_reason=hidden)
    s.add(a)
    s.flush()
    return a


def _track(s, artists, isrc=None, hidden=None, title=None):
    n = next(_n)
    c = CatalogEntry(
        title=title or f"t{n}",
        artist=", ".join(a.name for a in artists),
        normalized_key=f"k{n}",
        isrc=isrc,
        hidden_reason=hidden,
    )
    s.add(c)
    s.flush()
    for i, a in enumerate(artists):
        s.add(CatalogArtist(catalog_id=c.id, artist_id=a.id, position=i))
    s.flush()
    return c


def _user(s):
    n = next(_n)
    u = User(email=f"u{n}@x", username=f"u{n}", google_id=f"g{n}")
    s.add(u)
    s.flush()
    return u


def _in_set(s, c):
    st = DJSet(source="trackid", title="set", external_id=f"e{next(_n)}")
    s.add(st)
    s.flush()
    s.add(SetTrack(set_id=st.id, catalog_id=c.id, position=0))
    s.flush()


def _in_lib(s, c):
    s.add(UserTrack(user_id=_user(s).id, catalog_id=c.id))
    s.flush()


def _with_opinion(s, c):
    s.add(UserOpinion(user_id=_user(s).id, entity_type="track", entity_key=str(c.id), opinion="liked"))
    s.flush()


def _in_collection(s, c):
    col = UserCollection(user_id=_user(s).id, name="col")
    s.add(col)
    s.flush()
    s.add(CollectionItem(collection_id=col.id, item_type="track", item_id=c.id))
    s.flush()


def _tsv(*artists, genre="106", tier="2"):
    return [{"id": a.id if hasattr(a, "id") else a, "name": "", "tier": tier, "genre": genre} for a in artists]


def _reason(s, model, obj_id):
    s.expire_all()
    return s.get(model, obj_id).hidden_reason


def test_read_tsv_parses_and_skips_bad_lines():
    data = "945\tEmilio\t234\t38\t0\t0\t37\t1\t0.8\t106\t0.5\nbad\tx\n\n945\tdup\n12\tB\t1\t1\t0\t0\t0\t2\t1\t98\t1\n"
    rows, malformed = read_tsv(io.StringIO(data))
    assert [r["id"] for r in rows] == [945, 12]
    assert rows[0]["genre"] == "106" and rows[0]["tier"] == "1"
    assert rows[1]["genre"] == "98"
    assert malformed == 1


class TestFarmFort:
    def test_dry_run_writes_nothing(self, sync_session):
        s = sync_session
        a = _artist(s)
        c = _track(s, [a], isrc="GXLE12400001")
        s.commit()
        plan, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=False)
        assert stats["titles_to_mask"] == 1
        assert stats["artists_to_mask"] == 1
        assert _reason(s, CatalogEntry, c.id) is None
        assert _reason(s, Artist, a.id) is None

    def test_uncorroborated_masked_and_protections(self, sync_session):
        s = sync_session
        a = _artist(s)
        plain = _track(s, [a], isrc="QZAAA2400001")
        no_isrc = _track(s, [a], isrc=None)
        in_set = _track(s, [a], isrc="USYBL2400001")
        in_lib = _track(s, [a], isrc="FRXXX2400001")
        opin = _track(s, [a])
        coll = _track(s, [a])
        anchored = _track(s, [a], isrc="usybl2400099")  # same registrant, case-insensitive
        _in_set(s, in_set)
        _in_lib(s, in_lib)
        _with_opinion(s, opin)
        _in_collection(s, coll)
        s.commit()

        plan, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)

        assert _reason(s, CatalogEntry, plain.id) == "farm_fort"
        assert _reason(s, CatalogEntry, no_isrc.id) == "farm_fort"
        for c in (in_set, in_lib, opin, coll, anchored):
            assert _reason(s, CatalogEntry, c.id) is None
        assert s.get(CatalogEntry, plain.id).hidden_at is not None
        assert stats["titles_protected_corroborated"] == 4
        assert stats["titles_protected_anchored"] == 1
        assert stats["titles_masked"] == 2
        # titles remain visible → the artist stays visible
        assert _reason(s, Artist, a.id) is None
        assert stats["artists_kept_visible"] == 1

    def test_coartist_protection(self, sync_session):
        s = sync_session
        farm = _artist(s, "Farm")
        real = _artist(s, "Real")
        for _ in range(3):
            _in_set(s, _track(s, [real]))
        shared = _track(s, [farm, real], isrc="QZAAA2400002")
        weak = _artist(s, "Weak")
        _in_set(s, _track(s, [weak]))
        shared_weak = _track(s, [farm, weak], isrc="QZAAA2400003")
        s.commit()

        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(farm), apply=True)

        assert _reason(s, CatalogEntry, shared.id) is None
        assert _reason(s, CatalogEntry, shared_weak.id) == "farm_fort"
        assert stats["titles_protected_coartist"] == 1

    def test_coartist_in_tsv_never_protects(self, sync_session):
        s = sync_session
        farm = _artist(s, "Farm")
        bucket = _artist(s, "Bucket")  # TSV artist with many (false) corroborated titles
        for _ in range(3):
            _in_set(s, _track(s, [bucket]))
        shared = _track(s, [farm, bucket], isrc="QZAAA2400004")
        s.commit()

        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(farm, bucket), apply=True)

        assert _reason(s, CatalogEntry, shared.id) == "farm_fort"
        assert stats["titles_protected_coartist"] == 0

    def test_genre_guarded_tsv_coartist_still_protects(self, sync_session):
        s = sync_session
        farm = _artist(s, "Farm")
        jazz = _artist(s, "Jazz")  # TSV artist skipped by the genre guard
        for _ in range(3):
            _in_set(s, _track(s, [jazz]))
        shared = _track(s, [farm, jazz], isrc="QZAAA2400005")
        s.commit()
        rows = _tsv(farm) + _tsv(jazz, genre="129")

        _, stats = run_rule(s, "farm_fort", tsv_rows=rows, apply=True)

        assert _reason(s, CatalogEntry, shared.id) is None
        assert stats["titles_protected_coartist"] == 1

    def test_artist_masked_only_when_nothing_visible(self, sync_session):
        s = sync_session
        farm = _artist(s, "Farm")
        t1 = _track(s, [farm], isrc="GXLE12400002")
        t2 = _track(s, [farm], hidden="episode")  # other rule: not visible
        s.commit()

        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(farm), apply=True)

        assert _reason(s, CatalogEntry, t1.id) == "farm_fort"
        assert _reason(s, CatalogEntry, t2.id) == "episode"  # never rewritten
        assert stats["titles_already_other_rule"] == 1
        assert _reason(s, Artist, farm.id) == "farm_fort"
        assert stats["artists_masked"] == 1

    def test_genre_guard_and_missing_id(self, sync_session):
        s = sync_session
        classical = _artist(s, "Orch")
        jazz = _artist(s, "Jazz")
        c1 = _track(s, [classical])
        c2 = _track(s, [jazz])
        s.commit()
        rows = _tsv(classical, genre="98") + _tsv(jazz, genre="129") + _tsv(987654)

        _, stats = run_rule(s, "farm_fort", tsv_rows=rows, apply=True)

        assert stats["artists_genre_guard"] == 2
        assert stats["artists_missing"] == 1
        assert stats["titles_examined"] == 0
        assert _reason(s, CatalogEntry, c1.id) is None
        assert _reason(s, CatalogEntry, c2.id) is None

    def test_second_apply_is_noop(self, sync_session):
        s = sync_session
        a = _artist(s)
        c = _track(s, [a], isrc="GXLE12400003")
        s.commit()
        run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        first_at = s.get(CatalogEntry, c.id).hidden_at

        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)

        assert stats["titles_to_mask"] == 0
        assert stats["titles_already_same_rule"] == 1
        assert stats["artists_already_same_rule"] == 1
        assert stats["titles_masked"] == 0 and stats["artists_masked"] == 0
        s.expire_all()
        assert s.get(CatalogEntry, c.id).hidden_at == first_at

    def test_artist_hidden_by_other_rule_untouched(self, sync_session):
        s = sync_session
        a = _artist(s, hidden="manual")
        _track(s, [a])
        s.commit()
        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert _reason(s, Artist, a.id) == "manual"
        assert stats["artists_already_other_rule"] == 1


class TestIsrcBlock:
    def test_blocks_prefixes_with_protection(self, sync_session, monkeypatch):
        monkeypatch.delenv("CATALOG_ISRC_BLOCKED_PREFIXES", raising=False)
        s = sync_session
        a = _artist(s)
        blocked = _track(s, [a], isrc="gxle12345678")
        krb = _track(s, [a], isrc="KRB921234567")
        corro = _track(s, [a], isrc="GXLF12345678")
        other = _track(s, [a], isrc="USYBL1234567")
        prior = _track(s, [a], isrc="GXLE99999999", hidden="farm_fort")
        _in_set(s, corro)
        s.commit()

        _, stats = run_rule(s, "isrc_block", apply=True)

        assert _reason(s, CatalogEntry, blocked.id) == "isrc_block"
        assert _reason(s, CatalogEntry, krb.id) == "isrc_block"
        assert _reason(s, CatalogEntry, corro.id) is None
        assert _reason(s, CatalogEntry, other.id) is None
        assert _reason(s, CatalogEntry, prior.id) == "farm_fort"
        assert stats["titles_protected_corroborated"] == 1
        assert stats["titles_already_other_rule"] == 1
        # the artist keeps visible titles (corroborated / other ISRC) → stays visible
        assert _reason(s, Artist, a.id) is None
        assert stats["artists_kept_visible"] == 1

    def test_empty_prefixes_is_inert(self, sync_session, monkeypatch):
        monkeypatch.setenv("CATALOG_ISRC_BLOCKED_PREFIXES", "")
        s = sync_session
        c = _track(s, [_artist(s)], isrc="GXLE12345679")
        s.commit()
        _, stats = run_rule(s, "isrc_block", apply=True)
        assert stats["titles_examined"] == 0
        assert _reason(s, CatalogEntry, c.id) is None


class TestRevert:
    def test_revert_only_touches_requested_rule(self, sync_session):
        s = sync_session
        a1 = _artist(s, hidden="farm_fort")
        a2 = _artist(s, hidden="isrc_block")
        c1 = _track(s, [a1], hidden="farm_fort")
        c2 = _track(s, [a1], hidden="isrc_block")
        s.commit()

        assert revert_rule(s, "farm_fort", apply=False) == (1, 1)
        assert _reason(s, CatalogEntry, c1.id) == "farm_fort"  # dry-run

        assert revert_rule(s, "farm_fort", apply=True) == (1, 1)
        assert _reason(s, CatalogEntry, c1.id) is None
        assert s.get(CatalogEntry, c1.id).hidden_at is None
        assert _reason(s, Artist, a1.id) is None
        assert _reason(s, CatalogEntry, c2.id) == "isrc_block"
        assert _reason(s, Artist, a2.id) == "isrc_block"


# --------------------------------------------------------------------------- v2


def _bucket(s, artist, n=10):
    """Give ``artist`` n titles on n distinct registrants → top3 = 3/n."""
    return [_track(s, [artist], isrc=f"ZZ{i:03d}2400001") for i in range(n)]


def _concentrated(s, artist, n=10):
    """n titles on ONE registrant → top3 = 1.0 (farm profile)."""
    return [_track(s, [artist], isrc=f"GXLE1248{i:04d}") for i in range(n)]


class TestFarmFortV2Helpers:
    def test_isrc_year(self):
        assert isrc_year("QZAAA1500001") == 2015
        assert isrc_year("QZAAA9500001") == 1995
        assert isrc_year("QZAAA5000001") == 1950
        assert isrc_year("QZAAA4900001") == 2049
        assert isrc_year("QZAAAAB00001") is None  # non-numeric year chars
        assert isrc_year("QZAA") is None
        assert isrc_year(None) is None

    def test_classical_marker_is_narrow(self):
        assert has_classical_marker("Piano Concerto No. 3 in C Minor, Op. 37")
        assert has_classical_marker("Cello Suite BWV 1007")
        assert has_classical_marker("Tosca, Act II: Vissi d'arte")
        assert not has_classical_marker("Putaria")
        assert not has_classical_marker("Hot Symphony")

    def test_junk(self):
        assert is_junk("Midnight (Slowed + Reverb)", "X")
        assert is_junk("Track", "Relax Music Lab")
        assert is_junk("Track", "Deep Spa")  # "spa$"
        assert not is_junk("Track", "Mamba")

    def test_top3_share_and_br_funk(self):
        assert top3_share(["GXLE12400001"] * 5) == 1.0
        assert top3_share([f"ZZ{i:03d}2400001" for i in range(10)]) == 0.3
        # titles without (usable) ISRC form ONE group
        assert top3_share([None, None, "x", "AA0012400001"]) == 1.0
        assert is_br_funk_registrant("BCAB1") and is_br_funk_registrant("BXAB1")
        assert not is_br_funk_registrant("BRAB1") and not is_br_funk_registrant(None)


class TestFarmFortV2:
    def test_homonym_bucket_protected(self, sync_session):
        s = sync_session
        a = _artist(s, "Mamba")
        titles = _bucket(s, a)
        s.commit()
        plan, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert stats["titles_protected_homonym"] == 10
        assert stats["titles_to_mask"] == 0
        assert all(_reason(s, CatalogEntry, c.id) is None for c in titles)
        assert len(plan["homonym"]) == 10
        assert _reason(s, Artist, a.id) is None

    def test_bucket_junk_title_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Mamba")
        _bucket(s, a)
        junk = _track(s, [a], isrc="ZZ9992400001", title="Mamba (Slowed)")
        s.commit()
        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert _reason(s, CatalogEntry, junk.id) == "farm_fort"
        assert stats["titles_protected_homonym"] == 10

    def test_bucket_functional_artist_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Sleep Sounds")
        titles = _bucket(s, a)
        s.commit()
        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert stats["titles_protected_homonym"] == 0
        assert all(_reason(s, CatalogEntry, c.id) == "farm_fort" for c in titles)

    def test_bucket_br_funk_registrant_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Futura")
        _bucket(s, a)
        funk = _track(s, [a], isrc="BCAB12400001")
        funk_bk = _track(s, [a], isrc="bkab12400001")  # case-insensitive
        s.commit()
        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert _reason(s, CatalogEntry, funk.id) == "farm_fort"
        assert _reason(s, CatalogEntry, funk_bk.id) == "farm_fort"
        assert stats["titles_protected_homonym"] == 10

    def test_br_funk_only_loses_bucket_protection(self, sync_session):
        s = sync_session
        a = _artist(s, "Futura")
        _bucket(s, a)
        old_funk = _track(s, [a], isrc="BCAB11500001")  # 2015 → ISRC ancien applies
        s.commit()
        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert _reason(s, CatalogEntry, old_funk.id) is None
        assert stats["titles_protected_isrc_old"] == 1

    def test_concentrated_artist_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Farm")
        titles = _concentrated(s, a)
        s.commit()
        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert stats["titles_protected_homonym"] == 0
        assert stats["titles_to_mask"] == 10
        assert all(_reason(s, CatalogEntry, c.id) == "farm_fort" for c in titles)
        assert _reason(s, Artist, a.id) == "farm_fort"

    def test_isrc_years(self, sync_session):
        s = sync_session
        a = _artist(s, "Vega")
        _concentrated(s, a)
        old = _track(s, [a], isrc="QZAAA1500001")
        nineties = _track(s, [a], isrc="QZAAA9500001")
        no_year = _track(s, [a], isrc="QZAAAAB00001")
        recent = _track(s, [a], isrc="QZAAA2000001")  # 2020 > 2019
        s.commit()
        plan, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert _reason(s, CatalogEntry, old.id) is None
        assert _reason(s, CatalogEntry, nineties.id) is None
        assert _reason(s, CatalogEntry, no_year.id) == "farm_fort"
        assert _reason(s, CatalogEntry, recent.id) == "farm_fort"
        assert stats["titles_protected_isrc_old"] == 2
        assert {i["id"] for i in plan["isrc_old"]} == {old.id, nineties.id}

    def test_isrc_old_functional_artist_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Yoga Music")
        old = _track(s, [a], isrc="QZAAA1500001")
        s.commit()
        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert _reason(s, CatalogEntry, old.id) == "farm_fort"
        assert stats["titles_protected_isrc_old"] == 0

    def test_classical_marker(self, sync_session):
        s = sync_session
        a = _artist(s, "Orchestra X")
        _concentrated(s, a)
        opus = _track(s, [a], isrc="GXLE12490001", title="Piano Concerto No. 3, Op. 37")
        putaria = _track(s, [a], isrc="GXLE12490002", title="Putaria")
        junk_op = _track(s, [a], isrc="GXLE12490003", title="Nocturne Op. 9 (Sleep)")
        s.commit()
        plan, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert _reason(s, CatalogEntry, opus.id) is None
        assert _reason(s, CatalogEntry, putaria.id) == "farm_fort"
        assert _reason(s, CatalogEntry, junk_op.id) == "farm_fort"
        assert stats["titles_protected_classical"] == 1
        assert [i["id"] for i in plan["classical"]] == [opus.id]

    def test_priority_order(self, sync_session):
        s = sync_session
        a = _artist(s, "Elle")
        _bucket(s, a)
        corro = _track(s, [a], isrc="ZZ5002400001")
        _in_set(s, corro)
        classical = _track(s, [a], isrc="ZZ5012400001", title="Sonata Op. 2")
        old = _track(s, [a], isrc="ZZ5021500001")  # bucket AND old → bucket wins
        s.commit()
        plan, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=False)
        assert stats["titles_protected_corroborated"] == 1
        assert stats["titles_protected_classical"] == 1
        assert stats["titles_protected_homonym"] == 11  # 10 bucket + old
        assert stats["titles_protected_isrc_old"] == 0
        assert old.id in {i["id"] for i in plan["homonym"]}
        assert classical.id not in {i["id"] for i in plan["homonym"]}

    def test_second_apply_is_noop_with_bucket(self, sync_session):
        """Titles masked by this rule stay in the profile → stable bucket verdict."""
        s = sync_session
        a = _artist(s, "Mamba")
        _bucket(s, a, n=5)
        # 5 junk titles on 5 more registrants: masked, but kept in the profile
        for i in range(5):
            _track(s, [a], isrc=f"YY{i:03d}2400001", title="x (Slowed)")
        s.commit()
        _, first = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert first["titles_masked"] == 5 and first["titles_protected_homonym"] == 5
        _, second = run_rule(s, "farm_fort", tsv_rows=_tsv(a), apply=True)
        assert second["titles_to_mask"] == 0
        assert second["titles_protected_homonym"] == 5
        assert second["titles_already_same_rule"] == 5

    def test_report_prints_new_counters_and_samples(self, sync_session, capsys):
        s = sync_session
        bucket = _artist(s, "Mamba")
        _bucket(s, bucket)
        vega = _artist(s, "Vega")
        _track(s, [vega], isrc="QZAAA1500001", title="Old One")
        _track(s, [vega], isrc="QZAAA2400001", title="Concerto, Op. 37")
        s.commit()
        plan, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(bucket, vega), apply=False)
        _print_report("farm_fort", stats, plan, apply=False, sample_n=3)
        out = capsys.readouterr().out
        assert "protégés classique         : 1" in out
        assert "protégés seau homonymes    : 10" in out
        assert "protégés ISRC ancien       : 1" in out
        assert "3 titre(s) protégé(s) — seau homonymes" in out
        assert "1 titre(s) protégé(s) — marqueur classique" in out
        assert "1 titre(s) protégé(s) — ISRC ancien" in out
        assert "Vega — Concerto, Op. 37 — QZAAA2400001" in out
        assert "Vega — Old One — QZAAA1500001" in out


# --------------------------------------------------------------------------- episode


def _album(s, title, artist):
    al = Album(title=title, artist_id=artist.id if artist is not None else None)
    s.add(al)
    s.flush()
    return al


def _on_album(s, album, artists, **kw):
    c = _track(s, artists, **kw)
    s.add(CatalogAlbum(catalog_id=c.id, album_id=album.id))
    s.flush()
    return c


def _series(s, artist, pattern, numbers, per_album=2):
    """One album per number (title = pattern.format(n)), ``per_album`` titles each."""
    out = []
    for n in numbers:
        al = _album(s, pattern.format(n=n), artist)
        out += [_on_album(s, al, [artist]) for _ in range(per_album)]
    return out


class TestEpisodeHelpers:
    def test_series_key_folds_numbers_and_punctuation(self):
        k1 = series_key("ASOT 974 - A State Of Trance Episode 974")
        k2 = series_key("ASOT 1003 - A State Of Trance Episode 1003")
        assert k1 == k2 == "asot # a state of trance episode #"
        assert series_key("Défected Radio  Show #12") == series_key("Defected Radio Show 13")
        assert series_key(None) == ""

    def test_vocabulary(self):
        assert is_episode_series_key(series_key("Toolroom Radio EP612"))
        assert is_episode_series_key(series_key("FSOE 700 - Future Sound Of Egypt"))
        assert is_episode_series_key(series_key("Group Therapy 550"))
        assert not is_episode_series_key(series_key("Speicher 101"))
        assert not is_episode_series_key(series_key("Remixes Vol. 2 (Radio Edits)"))
        assert not is_episode_series_key("")
        # generic word: needs EPISODE_KEY_MIN_EXTRA_WORDS (2) other words
        assert not is_episode_series_key(series_key("Radio 3"))
        assert not is_episode_series_key(series_key("Radio Show 3"))
        assert is_episode_series_key(series_key("Club Night Radio Show 3"))
        # named shows are exempt (the ASOT key has one word outside its vocabulary)
        assert is_episode_series_key(series_key("ASOT 974 - A State Of Trance Episode 974"))
        assert is_episode_series_key(series_key("Defected Radio 123"))
        assert is_episode_series_key(series_key("Interplay Radio 300"))

    def test_title_marker(self):
        assert has_episode_marker("Que Pasa (ASOT 977) [Tune Of The Week]")
        assert has_episode_marker("A State Of Trance (asot 1003) (Shout Outs, Pt. 2)")
        assert not has_episode_marker("ASOT 977")
        assert not has_episode_marker(None)


class TestEpisode:
    def test_series_of_three_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Host")
        titles = _series(s, a, "Club Night Radio Show {n}", (101, 102, 103))
        s.commit()
        plan, stats = run_rule(s, "episode", apply=True)
        assert all(_reason(s, CatalogEntry, c.id) == "episode" for c in titles)
        assert stats["titles_masked"] == 6
        assert stats["titles_via_series"] == 6 and stats["titles_via_marker"] == 0
        assert stats["series_retained"] == 1
        assert plan["series"][0] == {
            "key": "club night radio show #",
            "artist_id": a.id,
            "artist": "Host",
            "albums": 3,
            "titles": 6,
        }

    def test_series_of_two_not_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Host")
        titles = _series(s, a, "Club Night Radio Show {n}", (101, 102))
        s.commit()
        _, stats = run_rule(s, "episode", apply=True)
        assert stats["series_retained"] == 0
        assert all(_reason(s, CatalogEntry, c.id) is None for c in titles)

    def test_label_series_without_vocabulary_not_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Label")
        titles = _series(s, a, "Speicher {n}", range(101, 106))
        s.commit()
        _, stats = run_rule(s, "episode", apply=True)
        assert stats["series_retained"] == 0 and stats["titles_to_mask"] == 0
        assert all(_reason(s, CatalogEntry, c.id) is None for c in titles)

    def test_series_split_across_album_artists_masked(self, sync_session):
        """Inverted by the correctif: a series no longer needs a common album artist
        (albums.artist_id is NULL on ~90 % of the prod episode albums)."""
        s = sync_session
        titles = []
        for name, n in (("A", 1), ("B", 2), ("C", 3)):
            titles += _series(s, _artist(s, name), "Club Night Radio Show {n}", (n,))
        s.commit()
        _, stats = run_rule(s, "episode", apply=True)
        assert stats["series_retained"] == 1
        assert all(_reason(s, CatalogEntry, c.id) == "episode" for c in titles)

    def test_series_without_album_artist_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Host")
        titles = []
        for n in (1, 2, 3):
            titles.append(_on_album(s, _album(s, f"Club Night Radio Show {n}", None), [a]))
        s.commit()
        plan, stats = run_rule(s, "episode", apply=True)
        assert stats["series_retained"] == 1
        assert all(_reason(s, CatalogEntry, c.id) == "episode" for c in titles)
        assert plan["series"][0]["artist"] == "Host"  # from catalog_artists credits

    def test_generic_key_without_extra_words_not_retained(self, sync_session):
        s = sync_session
        titles = []
        for n in (1, 2, 3):
            titles.append(_on_album(s, _album(s, f"Radio {n}", None), [_artist(s, "X")]))
        s.commit()
        _, stats = run_rule(s, "episode", apply=True)
        assert stats["series_retained"] == 0
        assert all(_reason(s, CatalogEntry, c.id) is None for c in titles)

    def test_title_also_on_regular_album_protected(self, sync_session):
        s = sync_session
        a = _artist(s, "Host")
        t = _series(s, a, "Club Night Radio Show {n}", (1, 2, 3), per_album=1)
        regular = _album(s, "Original Single", a)
        s.add(CatalogAlbum(catalog_id=t[0].id, album_id=regular.id))
        s.commit()
        plan, stats = run_rule(s, "episode", apply=True)
        assert _reason(s, CatalogEntry, t[0].id) is None
        assert stats["titles_protected_other_album"] == 1
        assert [i["id"] for i in plan["other_album"]] == [t[0].id]
        assert stats["titles_masked"] == 2
        assert _reason(s, Artist, a.id) is None  # its original stays visible

    def test_marker_title_on_regular_album_still_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Armin")
        c = _on_album(s, _album(s, "Original Single", a), [a], title="Que Pasa (ASOT 977)")
        s.commit()
        _, stats = run_rule(s, "episode", apply=True)
        assert _reason(s, CatalogEntry, c.id) == "episode"
        assert stats["titles_protected_other_album"] == 0

    def test_marker_and_series_title_on_regular_album_still_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Armin")
        t = _series(s, a, "ASOT {n} - A State Of Trance Episode {n}", (974, 975, 976), per_album=1)
        t[0].title = "Que Pasa (ASOT 974)"
        s.add(CatalogAlbum(catalog_id=t[0].id, album_id=_album(s, "Que Pasa", a).id))
        s.commit()
        _, stats = run_rule(s, "episode", apply=True)
        assert _reason(s, CatalogEntry, t[0].id) == "episode"
        assert stats["titles_protected_other_album"] == 0

    def test_report_artist_is_most_credited(self, sync_session, capsys):
        s = sync_session
        host, guest = _artist(s, "Host"), _artist(s, "Guest")
        for n in (1, 2, 3):
            al = _album(s, f"Club Night Radio Show {n}", guest)  # album artist ignored
            _on_album(s, al, [host])
            _on_album(s, al, [host, guest] if n == 1 else [host])
        s.commit()
        plan, stats = run_rule(s, "episode", apply=False)
        assert plan["series"][0]["artist_id"] == host.id
        _print_report("episode", stats, plan, apply=False, sample_n=3)
        out = capsys.readouterr().out
        assert f"     6 |      3 | Host ({host.id}) | club night radio show #" in out
        assert "protégés (aussi sur un album hors épisode) : 0" in out

    def test_isolated_next_episode_not_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Dre")
        c = _on_album(s, _album(s, "The Next Episode", a), [a])
        s.commit()
        _, stats = run_rule(s, "episode", apply=True)
        assert _reason(s, CatalogEntry, c.id) is None
        assert stats["titles_examined"] == 0

    def test_title_marker_without_album_masked(self, sync_session):
        s = sync_session
        a = _artist(s, "Armin")
        c = _track(s, [a], title="Que Pasa (ASOT 977) [Tune Of The Week]")
        plain = _track(s, [a], title="Blah (ASOT remix)")  # LIKE hit, regex miss
        s.commit()
        _, stats = run_rule(s, "episode", apply=True)
        assert _reason(s, CatalogEntry, c.id) == "episode"
        assert _reason(s, CatalogEntry, plain.id) is None
        assert stats["titles_via_marker"] == 1 and stats["titles_via_series"] == 0

    def test_episode_title_in_set_or_library_protected(self, sync_session):
        s = sync_session
        a = _artist(s, "Host")
        t = _series(s, a, "Club Night Radio Show {n}", (1, 2, 3), per_album=1)
        _in_set(s, t[0])
        _in_lib(s, t[1])
        s.commit()
        _, stats = run_rule(s, "episode", apply=True)
        assert _reason(s, CatalogEntry, t[0].id) is None
        assert _reason(s, CatalogEntry, t[1].id) is None
        assert _reason(s, CatalogEntry, t[2].id) == "episode"
        assert stats["titles_protected_corroborated"] == 2
        assert _reason(s, Artist, a.id) is None  # visible titles remain

    def test_other_rule_never_rewritten(self, sync_session):
        s = sync_session
        a = _artist(s, "Host")
        t = _series(s, a, "Club Night Radio Show {n}", (1, 2, 3), per_album=1)
        t[0].hidden_reason = "farm_fort"
        s.commit()
        _, stats = run_rule(s, "episode", apply=True)
        assert _reason(s, CatalogEntry, t[0].id) == "farm_fort"
        assert stats["titles_already_other_rule"] == 1
        assert stats["titles_masked"] == 2

    def test_second_apply_is_noop(self, sync_session):
        s = sync_session
        a = _artist(s, "Host")
        t = _series(s, a, "Club Night Radio Show {n}", (1, 2, 3), per_album=1)
        s.commit()
        _, first = run_rule(s, "episode", apply=True)
        assert first["titles_masked"] == 3 and first["artists_masked"] == 1
        first_at = s.get(CatalogEntry, t[0].id).hidden_at
        _, second = run_rule(s, "episode", apply=True)
        assert second["titles_to_mask"] == 0 and second["artists_to_mask"] == 0
        assert second["titles_already_same_rule"] == 3
        assert second["artists_already_same_rule"] == 1
        assert second["titles_masked"] == 0 and second["artists_masked"] == 0
        s.expire_all()
        assert s.get(CatalogEntry, t[0].id).hidden_at == first_at

    def test_revert_only_touches_episode(self, sync_session):
        s = sync_session
        a = _artist(s, "Host")
        t = _series(s, a, "Club Night Radio Show {n}", (1, 2, 3), per_album=1)
        other = _track(s, [_artist(s, "F")], hidden="farm_fort")
        s.commit()
        run_rule(s, "episode", apply=True)
        assert _reason(s, Artist, a.id) == "episode"
        assert revert_rule(s, "episode", apply=True) == (3, 1)
        assert all(_reason(s, CatalogEntry, c.id) is None for c in t)
        assert _reason(s, Artist, a.id) is None
        assert _reason(s, CatalogEntry, other.id) == "farm_fort"

    def test_report_prints_counters_and_series(self, sync_session, capsys):
        s = sync_session
        a = _artist(s, "Host")
        _series(s, a, "Club Night Radio Show {n}", (1, 2, 3))
        _track(s, [a], title="X (ASOT 1)")
        s.commit()
        plan, stats = run_rule(s, "episode", apply=False)
        _print_report("episode", stats, plan, apply=False, sample_n=3)
        out = capsys.readouterr().out
        assert "séries retenues            : 1" in out
        assert "titres à masquer           : 7" in out
        assert "dont via album de série  : 6" in out
        assert "dont via marqueur seul   : 1" in out
        assert "Séries retenues (1, par volume)" in out
        assert f"     6 |      3 | Host ({a.id}) | club night radio show #" in out
        assert "artistes à masquer         : 1" in out


# --------------------------------------------------------------------------- point B


class TestEmptyArtists:
    def test_isrc_block_masks_emptied_artist(self, sync_session, monkeypatch):
        monkeypatch.delenv("CATALOG_ISRC_BLOCKED_PREFIXES", raising=False)
        s = sync_session
        a = _artist(s, "Farm")
        _track(s, [a], isrc="GXLE12345001")
        _track(s, [a], isrc="GXLF12345002")
        s.add(ArtistCohort(artist_id=a.id, tier=1, computed_tier=1))
        s.commit()
        _, stats = run_rule(s, "isrc_block", apply=True)
        assert _reason(s, Artist, a.id) == "isrc_block"
        assert stats["artists_to_mask"] == 1 and stats["artists_to_mask_tier1"] == 1
        assert stats["artists_masked"] == 1

    def test_one_visible_title_keeps_artist(self, sync_session, monkeypatch):
        monkeypatch.delenv("CATALOG_ISRC_BLOCKED_PREFIXES", raising=False)
        s = sync_session
        a = _artist(s, "Mixed")
        _track(s, [a], isrc="GXLE12345003")
        _track(s, [a], isrc="USYBL1234500")
        s.commit()
        _, stats = run_rule(s, "isrc_block", apply=True)
        assert _reason(s, Artist, a.id) is None
        assert stats["artists_kept_visible"] == 1 and stats["artists_to_mask"] == 0

    def test_emptied_by_mix_of_rules_masked_by_current(self, sync_session, monkeypatch):
        monkeypatch.delenv("CATALOG_ISRC_BLOCKED_PREFIXES", raising=False)
        s = sync_session
        a = _artist(s, "Both")
        _track(s, [a], isrc="QZAAA2400001", hidden="farm_fort")
        _track(s, [a], isrc="GXLE12345004")
        s.commit()
        run_rule(s, "isrc_block", apply=True)
        assert _reason(s, Artist, a.id) == "isrc_block"

    def test_artist_without_title_never_masked(self, sync_session, monkeypatch):
        monkeypatch.delenv("CATALOG_ISRC_BLOCKED_PREFIXES", raising=False)
        s = sync_session
        lonely = _artist(s, "Lonely")
        _track(s, [_artist(s, "Farm")], isrc="GXLE12345005")
        s.commit()
        run_rule(s, "isrc_block", apply=True)
        assert _reason(s, Artist, lonely.id) is None

    def test_only_other_rule_titles_not_masked_by_current(self, sync_session, monkeypatch):
        """No title masked by THIS rule → the artist is not this rule's business."""
        monkeypatch.delenv("CATALOG_ISRC_BLOCKED_PREFIXES", raising=False)
        s = sync_session
        a = _artist(s, "Other")
        _track(s, [a], isrc="QZAAA2400002", hidden="farm_fort")
        _track(s, [_artist(s, "Farm")], isrc="GXLE12345006")
        s.commit()
        run_rule(s, "isrc_block", apply=True)
        assert _reason(s, Artist, a.id) is None

    def test_revert_unmasks_artist(self, sync_session, monkeypatch):
        monkeypatch.delenv("CATALOG_ISRC_BLOCKED_PREFIXES", raising=False)
        s = sync_session
        a = _artist(s, "Farm")
        c = _track(s, [a], isrc="GXLE12345007")
        s.commit()
        run_rule(s, "isrc_block", apply=True)
        assert _reason(s, Artist, a.id) == "isrc_block"
        assert revert_rule(s, "isrc_block", apply=True) == (1, 1)
        assert _reason(s, Artist, a.id) is None
        assert _reason(s, CatalogEntry, c.id) is None

    def test_farm_fort_coartist_outside_tsv_counted_apart(self, sync_session):
        s = sync_session
        farm = _artist(s, "Farm")
        feat = _artist(s, "Feat")  # only credited on a farm title, not in the TSV
        _track(s, [farm, feat], isrc="GXLE12400100")
        s.commit()
        _, stats = run_rule(s, "farm_fort", tsv_rows=_tsv(farm), apply=True)
        assert stats["artists_to_mask"] == 1  # TSV counter unchanged
        assert stats["artists_to_mask_coartists"] == 1
        assert _reason(s, Artist, farm.id) == "farm_fort"
        assert _reason(s, Artist, feat.id) == "farm_fort"
        assert stats["artists_masked"] == 2
