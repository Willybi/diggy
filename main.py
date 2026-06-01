from pyrekordbox import Rekordbox6Database

db = Rekordbox6Database()
tracks = list(db.get_content())

# Tout ce qu'on peut extraire par track
for track in tracks[:3]:
    print(f"{track.Title}")
    print(f"  Artist  : {track.Artist.Name}")
    print(f"  BPM     : {round(track.BPM / 100, 1)}")
    print(f"  Key     : {track.Key}")
    print(f"  Rating  : {track.Rating}")
    print(f"  My Tags : {track.MyTagNames}")
    print(f"  File    : {track.FolderPath}")