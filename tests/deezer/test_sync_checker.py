from server.deezer.sync_checker import check_sync, FlagType


def dz_track(title: str, artist: str) -> dict:
    return {"title": title, "artist": {"name": artist}}


def rb_track(title: str, artist: str, tags: list[str], rating: int = 3) -> dict:
    return {"title": title, "artist": artist, "tags": tags, "rating": rating}


class TestDownloadNeeded:
    def test_detects_track_on_deezer_not_in_rb(self):
        deezer = {"W - Tech House": [dz_track("Body Funk", "Purple Disco Machine")]}
        rb = {"Tech House": []}
        report = check_sync(deezer, rb)
        flags = report.by_type(FlagType.DOWNLOAD_NEEDED)
        assert len(flags) == 1
        assert flags[0].title == "Body Funk"
        assert flags[0].deezer_playlist == "W - Tech House"

    def test_no_flag_when_present_in_rb(self):
        deezer = {"W - Tech House": [dz_track("Body Funk", "Purple Disco Machine")]}
        rb = {"Tech House": [rb_track("Body Funk", "Purple Disco Machine", ["Tech House"])]}
        report = check_sync(deezer, rb)
        assert report.by_type(FlagType.DOWNLOAD_NEEDED) == []


class TestAnomaly:
    def test_detects_track_in_rb_not_on_deezer(self):
        deezer = {"W - Tech House": []}
        rb = {"Tech House": [rb_track("Mystery Track", "Unknown", ["Tech House"])]}
        report = check_sync(deezer, rb)
        flags = report.by_type(FlagType.ANOMALY)
        assert len(flags) == 1
        assert flags[0].title == "Mystery Track"

    def test_soundcloud_track_not_flagged(self):
        deezer = {"W - Tech House": []}
        rb = {"Tech House": [rb_track("SC Track", "Artist", ["Tech House", "SoundCloud"])]}
        report = check_sync(deezer, rb)
        assert report.by_type(FlagType.ANOMALY) == []


class TestMisplaced:
    def test_detects_track_in_wrong_rb_tag(self):
        # Sur Deezer dans Nu Disco, dans RB sous Tech House
        deezer = {
            "W - Nu Disco": [dz_track("Body Funk", "Purple Disco Machine")],
            "W - Tech House": [],
        }
        rb = {
            "Nu Disco": [],
            "Tech House": [rb_track("Body Funk", "Purple Disco Machine", ["Tech House"])],
        }
        report = check_sync(deezer, rb)
        flags = report.by_type(FlagType.MISPLACED)
        assert len(flags) == 1
        assert flags[0].title == "Body Funk"
        assert flags[0].deezer_playlist == "W - Nu Disco"
        assert flags[0].rb_tag == "Tech House"

    def test_detects_track_in_wrong_deezer_playlist(self):
        # Dans RB sous Nu Disco, sur Deezer dans Tech House
        deezer = {
            "W - Nu Disco": [],
            "W - Tech House": [dz_track("Body Funk", "Purple Disco Machine")],
        }
        rb = {
            "Nu Disco": [rb_track("Body Funk", "Purple Disco Machine", ["Nu Disco"])],
            "Tech House": [],
        }
        report = check_sync(deezer, rb)
        flags = report.by_type(FlagType.MISPLACED)
        assert len(flags) == 1
        assert flags[0].title == "Body Funk"


class TestNormalize:
    def test_ft_dot_matches_ft(self):
        deezer = {"W - UK House": [dz_track("Talk To You (ft. 54 Ultra)", "ANOTR")]}
        rb = {"UK House": [rb_track("Talk To You (ft 54 Ultra)", "ANOTR", ["UK House"])]}
        report = check_sync(deezer, rb)
        assert report.by_type(FlagType.DOWNLOAD_NEEDED) == []
        assert report.by_type(FlagType.ANOMALY) == []

    def test_nu_disco_tag_fuzzy_match(self):
        deezer = {"W - Nu Disco": [dz_track("Body Funk", "Purple Disco Machine")]}
        rb = {"Nu-Disco": [rb_track("Body Funk", "Purple Disco Machine", ["Nu-Disco"])]}
        report = check_sync(deezer, rb)
        assert report.by_type(FlagType.DOWNLOAD_NEEDED) == []

    def test_no_false_positive_on_different_artists(self):
        deezer = {"W - Tech House": [dz_track("Adrenaline", "Airod")]}
        rb = {"Tech House": [rb_track("Adrenaline", "ADB", ["Tech House"])]}
        # Même titre, artistes différents — on match sur titre seul donc pas de flag
        report = check_sync(deezer, rb)
        assert report.by_type(FlagType.DOWNLOAD_NEEDED) == []


class TestSummary:
    def test_summary_empty(self):
        report = check_sync({}, {})
        summary = report.summary()
        assert "[DOWNLOAD_NEEDED] (0)" in summary
        assert "aucune entrée" in summary

    def test_summary_shows_flags(self):
        deezer = {"W - Tech House": [dz_track("Body Funk", "Purple Disco Machine")]}
        rb = {"Tech House": []}
        report = check_sync(deezer, rb)
        summary = report.summary()
        assert "DOWNLOAD_NEEDED" in summary
        assert "Body Funk" in summary
