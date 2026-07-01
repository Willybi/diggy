import re


def normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = re.sub(r"\bft\.", "ft", s)
    s = re.sub(r"\bfeat\.", "feat", s)
    return s


def make_normalized_key(title: str, artist: str | None) -> str:
    return normalize(title) + " - " + normalize(artist or "")
