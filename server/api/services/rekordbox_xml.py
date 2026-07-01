"""Parser for Rekordbox XML export files (Fichier > Exporter la collection > XML)."""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

logger = logging.getLogger("diggy")


def validate_rekordbox_xml(content: bytes) -> bool:
    """Return True if content looks like a valid Rekordbox XML export."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return False
    return root.tag == "DJ_PLAYLISTS" and root.get("Version") is not None


def parse_rekordbox_xml(content: bytes) -> list:
    """Parse Rekordbox XML and return a list of TrackImport objects."""
    from schemas import TrackImport

    root = ET.fromstring(content)
    collection = root.find("COLLECTION")
    if collection is None:
        logger.warning("No COLLECTION node found in Rekordbox XML")
        return []

    tracks = []
    for elem in collection.findall("TRACK"):
        track_id_str = elem.get("TrackID")
        name = elem.get("Name")

        if not track_id_str or not name:
            logger.debug("Skipping TRACK without TrackID or Name: %s", elem.attrib)
            continue

        try:
            track_id = int(track_id_str)
        except ValueError:
            logger.warning("Invalid TrackID '%s', skipping", track_id_str)
            continue

        bpm: Optional[float] = None
        bpm_str = elem.get("AverageBpm")
        if bpm_str:
            try:
                bpm = float(bpm_str)
            except ValueError:
                pass

        duration: Optional[int] = None
        total_time_str = elem.get("TotalTime")
        if total_time_str:
            try:
                duration = int(total_time_str) * 1000
            except ValueError:
                pass

        rating: Optional[int] = None
        rating_str = elem.get("Rating")
        if rating_str:
            try:
                # Rekordbox stores ratings as 0/51/102/153/204/255, convert to 0-5
                rating = round(int(rating_str) / 51)
            except ValueError:
                pass

        date_added: Optional[datetime] = None
        date_str = elem.get("DateAdded")
        if date_str:
            try:
                date_added = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                pass

        tracks.append(
            TrackImport(
                id=track_id,
                title=name,
                artist=elem.get("Artist") or None,
                bpm=bpm,
                key=elem.get("Tonality") or None,
                duration=duration,
                rating=rating,
                date_added=date_added,
                file_path=elem.get("Location") or None,
                tags=[],
                image_base64=None,
            )
        )

    return tracks
