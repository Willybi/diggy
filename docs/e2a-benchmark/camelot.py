"""Camelot conversion + harmonic-neighbor + BPM octave-fold helpers for the E2.a benchmark.

The key->Camelot mapping is spelling-independent (pitch-class based) so it is robust to
whatever enharmonic spelling Essentia/librosa emit ('F#' vs 'Gb', 'Ab' vs 'G#').
Cross-checked against the repo's Beatport table `_KEY_TO_CAMELOT`
(server/api/beatport/client.py:26-66) — e.g. A Minor->8A, C Major->8B, F# Minor->11A, F# Major->2B.
"""

_NOTE_TO_PC = {
    "C": 0, "B#": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4, "E#": 5, "F": 5, "F#": 6, "Gb": 6, "G": 7,
    "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11, "Cb": 11,
}

# pitch class (0=C .. 11=B) -> Camelot, per mode (standard Camelot wheel)
_MAJOR_PC = {0: "8B", 1: "3B", 2: "10B", 3: "5B", 4: "12B", 5: "7B",
             6: "2B", 7: "9B", 8: "4B", 9: "11B", 10: "6B", 11: "1B"}
_MINOR_PC = {0: "5A", 1: "12A", 2: "7A", 3: "2A", 4: "9A", 5: "4A",
             6: "11A", 7: "6A", 8: "1A", 9: "8A", 10: "3A", 11: "10A"}


def key_to_camelot(note, scale):
    """('F#', 'minor') -> '11A'. Returns None if unparseable."""
    if not note or not scale:
        return None
    pc = _NOTE_TO_PC.get(note.strip())
    if pc is None:
        return None
    s = scale.strip().lower()
    if s.startswith("min"):
        return _MINOR_PC[pc]
    if s.startswith("maj"):
        return _MAJOR_PC[pc]
    return None


def _parse(cam):
    cam = cam.strip().upper()
    return int(cam[:-1]), cam[-1]


def camelot_neighbors(cam):
    """Harmonically-compatible set INCLUDING self: self, relative (same number,
    other letter), +1 and -1 same letter (wheel wraps 1..12)."""
    num, letter = _parse(cam)
    other = "B" if letter == "A" else "A"
    nxt = num % 12 + 1
    prv = (num - 2) % 12 + 1
    return {f"{num}{letter}", f"{num}{other}", f"{nxt}{letter}", f"{prv}{letter}"}


def bpm_fold(analyzed, truth):
    """STRICT octave fold (x2 / /2 only) — the roadmap's definition. Returns (best, abs_err)."""
    cands = [analyzed, analyzed * 2.0, analyzed / 2.0]
    best = min(cands, key=lambda c: abs(c - truth))
    return best, abs(best - truth)


# Extended metrical multiples: octave (x2), triple-feel (x3), and 3:2 / 4:3 dotted/triplet
# relationships that beat trackers commonly mislabel on halftime/breakbeat material.
_EXT_RATIOS = (1.0, 2.0, 0.5, 3.0, 1 / 3, 1.5, 2 / 3, 4 / 3, 0.75)


def bpm_fold_ext(analyzed, truth):
    """EXTENDED metrical fold (x2,/2,x3,/3,x1.5,x2/3,x4/3,x3/4). Returns (best, abs_err).
    Measures the ceiling if metrical ambiguity (not just octave) is treated as 'right tempo'."""
    cands = [analyzed * r for r in _EXT_RATIOS]
    best = min(cands, key=lambda c: abs(c - truth))
    return best, abs(best - truth)
