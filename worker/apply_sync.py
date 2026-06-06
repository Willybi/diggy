"""
Applique les corrections MISPLACED détectées par check_sync.

Pour chaque track MISPLACED, déplace le fichier MP3 vers le dossier correspondant
à la playlist Deezer (source de vérité) et met à jour FolderPath dans la DB RB.
"""

import os
import shutil
import sys

from pyrekordbox import Rekordbox6Database

from server.deezer.sync_checker import FlagType, SyncReport
from worker.rekordbox.extractor import RekordboxExtractor
from worker.relocate_tracks import TAG_TO_FOLDER, W_MIX_ROOT
from server.deezer.sync_checker import _normalize


def _playlist_to_folder(deezer_playlist: str) -> str:
    style = deezer_playlist.removeprefix("W - ")
    folder_name = TAG_TO_FOLDER.get(style, f"W - {style}")
    return os.path.join(W_MIX_ROOT, folder_name)


def apply_misplaced(report: SyncReport, dry_run: bool = False) -> None:
    flags = report.by_type(FlagType.MISPLACED)
    if not flags:
        return

    rb = RekordboxExtractor()
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        db = Rekordbox6Database()
        sys.stdout = old_stdout
    moved = 0
    errors = 0

    for flag in flags:
        target_folder = _playlist_to_folder(flag.deezer_playlist)
        title_key = _normalize(flag.title)

        # Cherche le track dans RB par tag et titre normalisé
        candidates = [
            t for t in rb.get_tracks_by_tag(flag.rb_tag)
            if _normalize(t.Title or "") == title_key and t.rb_data_status == 256
        ]
        if not candidates:
            print(f"  [INTROUVABLE] {flag.artist} — {flag.title} (tag RB: {flag.rb_tag})")
            errors += 1
            continue

        track = candidates[0]
        current_path = track.OrgFolderPath or track.FolderPath
        filename = os.path.basename(current_path)
        target_path = os.path.join(target_folder, filename)

        if os.path.normcase(current_path) == os.path.normcase(target_path):
            print(f"  [DEJA OK]  {flag.artist} — {flag.title}")
            continue

        print(f"  [MOVE]  {flag.artist} — {flag.title}")
        print(f"          {current_path}")
        print(f"       -> {target_path}")

        if dry_run:
            continue

        try:
            if not os.path.exists(current_path):
                print(f"    [ERREUR] Fichier source introuvable : {current_path}")
                errors += 1
                continue

            os.makedirs(target_folder, exist_ok=True)

            if os.path.exists(target_path):
                print(f"    [ERREUR] Fichier déjà présent à destination : {target_path}")
                errors += 1
                continue

            shutil.move(current_path, target_path)

            # Récupère le track depuis la DB pour mise à jour
            db_track = next(
                (t for t in db.get_content() if t.ID == track.ID), None
            )
            if db_track:
                db_track.OrgFolderPath = target_path
                db_track.FolderPath = target_path

            moved += 1

        except Exception as e:
            print(f"    [ERREUR] {e}")
            errors += 1

    if not dry_run and moved > 0:
        print(f"\nSauvegarde dans Rekordbox...")
        db.session.commit()

    label = "(dry-run) " if dry_run else ""
    print(f"\n--- apply_sync {label}---")
    print(f"  Déplacés : {moved}")
    print(f"  Erreurs  : {errors}")
