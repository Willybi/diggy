"""
Lance la comparaison Deezer ↔ Rekordbox et affiche le rapport de sync.

Usage:
    python -m worker.check_sync
    python -m worker.check_sync --dry-run   # prévisualise les déplacements MISPLACED
    python -m worker.check_sync --apply     # déplace les fichiers et met à jour la DB RB
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.deezer.extractor import DeezerExtractor
from server.deezer.sync_checker import check_sync
from worker.rekordbox.extractor import RekordboxExtractor

DEEZER_USER_ID = "656772321"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Déplace les fichiers MISPLACED et met à jour la DB RB")
    parser.add_argument("--dry-run", action="store_true", help="Prévisualise les déplacements sans les effectuer")
    args = parser.parse_args()

    print("Récupération des playlists Deezer...")
    dz = DeezerExtractor(DEEZER_USER_ID)
    deezer_playlists = dz.get_all_tracks()
    print(f"  {len(deezer_playlists)} playlists W - trouvées.")

    print("Lecture des tags Rekordbox...")
    rb = RekordboxExtractor()
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        tags_structure = rb.get_tags_structure()
        sys.stdout = old_stdout

    rb_by_tag = {}
    for tag_name in [tag for tags in tags_structure.values() for tag in tags
                     if not tag.upper().startswith("TO_")]:
        tracks = rb.get_tracks_by_tag(tag_name)
        rb_by_tag[tag_name] = [
            {
                "title": t.Title,
                "artist": t.ArtistName,
                "tags": list(t.MyTagNames or []),
                "rating": t.Rating or 0,
            }
            for t in tracks
            if t.rb_data_status == 256
        ]
    print(f"  {len(rb_by_tag)} tags RB chargés.")

    print("\nComparaison en cours...\n")
    report = check_sync(deezer_playlists, rb_by_tag)
    print(report.summary())

    if args.apply or args.dry_run:
        from worker.apply_sync import apply_misplaced
        print()
        apply_misplaced(report, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
