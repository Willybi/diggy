"""
Script de relocalisation des tracks Rekordbox.

Vérifie que chaque track actif est dans le bon dossier W_MIX selon son tag style,
déplace physiquement le fichier si besoin, et met à jour FolderPath dans Rekordbox.

Règles :
  - Tag style       → dossier attendu : W_MIX_ROOT / "W - {tag}"
  - Tag soundcloud  → dossier attendu : W_MIX_ROOT / "_IMPORT"
  - Pas de tag      → signalé, aucune action

Usage :
    python relocate_tracks.py [--dry-run]
"""

import argparse
import os
import shutil

from pyrekordbox import Rekordbox6Database

W_MIX_ROOT = r"C:\Users\willi\Music\W_MIX"

# Correspondances tag RB → nom exact du dossier (quand ils diffèrent)
TAG_TO_FOLDER: dict[str, str] = {
    "Classic/Min. Techno": "W - Classic_Min. Techno",
    "Hard/Dark Techno":    "W - Hard_Dark Techno",
    "Nu-Disco":            "W - Nu Disco",
}

SOUNDCLOUD_TAG = "soundcloud"

# Les tags utilitaires ne correspondent pas à un style musical
def _is_style_tag(tag: str) -> bool:
    return not tag.upper().startswith("TO_") and tag.lower() != SOUNDCLOUD_TAG


def get_style_tag(tag_names: list[str]) -> str | None:
    """Retourne le premier tag style (ni TO_*, ni soundcloud), ou None."""
    for tag in tag_names:
        if _is_style_tag(tag):
            return tag
    return None


def expected_folder(tag_names: list[str]) -> str | None:
    """
    Retourne le chemin du dossier attendu pour un track selon ses tags.
    Retourne None si aucun tag style trouvé (pas d'action possible).
    """
    tags_lower = [t.lower() for t in tag_names]

    if SOUNDCLOUD_TAG in tags_lower:
        return os.path.join(W_MIX_ROOT, "_IMPORT")

    style = get_style_tag(tag_names)
    if style:
        folder_name = TAG_TO_FOLDER.get(style, f"W - {style}")
        return os.path.join(W_MIX_ROOT, folder_name)

    return None


def relocate_tracks(dry_run: bool = False):
    print("Connexion a Rekordbox...")
    db = Rekordbox6Database()

    tracks = [t for t in db.get_content() if t.rb_data_status == 256]
    print(f"{len(tracks)} tracks actifs trouves.\n")

    moved = 0
    already_ok = 0
    no_tag = 0
    errors = 0

    for track in tracks:
        tag_names = list(track.MyTagNames or [])
        current_path = track.OrgFolderPath or track.FolderPath

        if not tag_names:
            print(f"[NO TAG]  {track.ArtistName} - {track.Title}")
            no_tag += 1
            continue

        target_folder = expected_folder(tag_names)
        if target_folder is None:
            print(f"[NO TAG]  {track.ArtistName} - {track.Title}")
            no_tag += 1
            continue

        filename = os.path.basename(current_path)
        target_path = os.path.join(target_folder, filename)

        # Normalise pour comparer (casse insensible sur Windows)
        if os.path.normcase(current_path) == os.path.normcase(target_path):
            already_ok += 1
            continue

        print(f"[MOVE]  {track.ArtistName} - {track.Title}")
        print(f"        {current_path}")
        print(f"     -> {target_path}")

        if not dry_run:
            try:
                if not os.path.exists(current_path):
                    print(f"  [ERREUR] Fichier source introuvable : {current_path}")
                    errors += 1
                    continue

                os.makedirs(target_folder, exist_ok=True)

                if os.path.exists(target_path):
                    print(f"  [ERREUR] Un fichier existe deja a destination : {target_path}")
                    errors += 1
                    continue

                shutil.move(current_path, target_path)
                track.OrgFolderPath = target_path
                track.FolderPath = target_path
                moved += 1

            except Exception as e:
                print(f"  [ERREUR] {e}")
                errors += 1

    if not dry_run and moved > 0:
        print(f"\nSauvegarde dans Rekordbox...")
        db.session.commit()

    print(f"\n--- Resultat {'(dry-run) ' if dry_run else ''}---")
    print(f"  Deja en place : {already_ok}")
    print(f"  Deplaces      : {moved}")
    print(f"  Sans tag      : {no_tag}")
    print(f"  Erreurs       : {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les deplacements sans les effectuer",
    )
    args = parser.parse_args()

    relocate_tracks(dry_run=args.dry_run)
