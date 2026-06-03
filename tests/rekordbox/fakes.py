"""Faux objets imitant les modèles pyrekordbox pour les tests."""


class FakeKey:
    def __init__(self, name):
        self.ScaleName = name


class FakeMyTag:
    def __init__(self, name):
        self.Name = name


class FakeSongMyTag:
    def __init__(self, content, tag_name):
        self.Content = content
        self.MyTag = FakeMyTag(tag_name)


class FakeTag:
    def __init__(self, id, name, attribute, parent_id=None):
        self.ID = id
        self.Name = name
        self.Attribute = attribute  # 1 = groupe, 0 = tag
        self.ParentID = parent_id


class FakeCue:
    def __init__(self, content_id, kind, position_ms, color=-1, active_loop=None):
        self.ContentID = content_id
        self.Kind = kind
        self.InMsec = position_ms
        self.Color = color
        self.ActiveLoop = active_loop


class FakeTrack:
    def __init__(
        self,
        id,
        title,
        artist_name,
        bpm,
        key_name,
        length,
        rating,
        folder_path,
        date_created,
        my_tag_names,
        image_path=None,
        rb_data_status=256,
    ):
        self.ID = id
        self.Title = title
        self.ArtistName = artist_name
        self.BPM = bpm
        self.Key = FakeKey(key_name) if key_name else None
        self.Length = length
        self.Rating = rating
        self.FolderPath = folder_path
        self.DateCreated = date_created
        self.MyTagNames = my_tag_names
        self.ImagePath = image_path
        self.rb_data_status = rb_data_status


# Fixtures réutilisables

TRACKS = [
    FakeTrack(
        id=80011739,
        title="Wannabe",
        artist_name="VOLAC",
        bpm=12800,
        key_name="6A",
        length=165,
        rating=3,
        folder_path="C:/Music/Wannabe.mp3",
        date_created="2026-04-20",
        my_tag_names=["Tech House", "TO_CUE"],
        image_path="/PIONEER/Artwork/abc/123/artwork.jpg",
        rb_data_status=256,
    ),
    FakeTrack(
        id=52608202,
        title="Face to Face",
        artist_name="Daft Punk",
        bpm=11788,
        key_name="1A",
        length=240,
        rating=5,
        folder_path="C:/Music/FaceToFace.mp3",
        date_created="2026-04-20",
        my_tag_names=["French Touch"],
        image_path=None,
        rb_data_status=256,
    ),
    FakeTrack(
        id=99999999,
        title="Ghost Track",
        artist_name="Unknown",
        bpm=13000,
        key_name=None,
        length=300,
        rating=0,
        folder_path="C:/Music/ghost.mp3",
        date_created="2026-01-01",
        my_tag_names=[],
        image_path=None,
        rb_data_status=262,  # supprimé — ne doit pas être importé
    ),
]

CUES = [
    FakeCue(content_id=80011739, kind=1, position_ms=25, color=-1),       # Hot cue A
    FakeCue(content_id=80011739, kind=2, position_ms=30025, color=-1),    # Hot cue B
    FakeCue(content_id=80011739, kind=0, position_ms=15025, color=255),   # Memory cue
    FakeCue(content_id=52608202, kind=1, position_ms=1000, color=0, active_loop=1),  # Loop A
]

TAGS = [
    FakeTag(id=1, name="STYLE", attribute=1),
    FakeTag(id=2, name="PROCESS", attribute=1),
    FakeTag(id=3, name="Tech House", attribute=0, parent_id=1),
    FakeTag(id=4, name="French Touch", attribute=0, parent_id=1),
    FakeTag(id=5, name="TO_CUE", attribute=0, parent_id=2),
    FakeTag(id=6, name="EMPTY_TAG", attribute=0, parent_id=1),  # jamais assigné
]

SONG_MY_TAGS = [
    FakeSongMyTag(content=TRACKS[0], tag_name="Tech House"),
    FakeSongMyTag(content=TRACKS[0], tag_name="TO_CUE"),
    FakeSongMyTag(content=TRACKS[1], tag_name="French Touch"),
]
