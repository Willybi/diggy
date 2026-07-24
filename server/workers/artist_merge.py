"""Artist de-duplication primitive (sync worker context).

``artists.normalized_name`` (the identity key, UNIQUE) is accent-SENSITIVE:
``utils.normalize`` only lowercases, trims and folds a couple of quote/feat forms
— it does NOT fold accents or Unicode composition. The Deezer matcher, on the
other hand, folds accents (NFKD + ASCII, ``tasks/artists._norm_artist_name``). So
two spellings of ONE artist that differ only by an accent or a Unicode form
("Nick León" / "Nick Leon", an NFD vs NFC "Zoë") produce TWO ``artists`` rows:
the first one searched links to the Deezer id, and its twin is then blocked
forever by the partial-unique index ``uq_artists_deezer_id`` (it can never take
the same id). This module folds such an orphan ("source") into its linked twin
("target"):

    merge_artist_into(session, source_id, target_id)

It is the SYNC, reusable twin of the async merge branch in
``services.artist_service.link_to_deezer``: every ``set_artists`` /
``catalog_artists`` link of the source is reassigned to the target (dropping the
rows that would collide on the composite PK the target already holds), the
source's aliases are moved (honouring the UNIQUE ``normalized_alias``), the source
spelling is kept as an alias of the target, and the source row is deleted. All
repointing is bulk UPDATE/DELETE — no ORM relationship cascade.

The caller owns the transaction: this primitive NEVER commits, and it does NOT
touch the target's ``normalized_name`` (canonicalising the survivor is the driver
script's job, safe only once the source is gone). This lot ships the primitive
plus the one-shot ``scripts/dedup_artists_deezer.py`` cleanup that drives it; it
does not touch ``utils.normalize`` or the nightly link task.
"""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session


def _reassign_artist_links(session, model, other_pk, source_id, target_id):
    """Repoint ``model`` rows from ``source_id`` to ``target_id`` on ``artist_id``.

    ``model`` (``SetArtist`` / ``CatalogArtist``) has a composite PK
    ``(other_pk, artist_id)``; a source row for an ``other_pk`` value the target
    already links would collide on the PK once repointed, so it is dropped first
    (the target already carries that link — no information is lost), then the
    survivors are moved in place. ``synchronize_session=False`` because these ORM
    rows are never read back in this unit of work — same two-step as
    ``link_to_deezer`` and ``catalog_merge._repoint_composite``.
    """
    session.execute(
        delete(model)
        .where(
            model.artist_id == source_id,
            other_pk.in_(select(other_pk).where(model.artist_id == target_id)),
        )
        .execution_options(synchronize_session=False)
    )
    session.execute(
        update(model)
        .where(model.artist_id == source_id)
        .values(artist_id=target_id)
        .execution_options(synchronize_session=False)
    )


def _move_aliases(session, ArtistAlias, source_id, target):
    """Move the source's aliases to the target, honouring UNIQUE ``normalized_alias``.

    A source alias whose ``normalized_alias`` is already taken on the target —
    either by one of the target's own aliases or by the target's
    ``normalized_name`` (an alias equal to the canonical name is redundant) — is
    dropped instead of moved; the rest are repointed. This MUST run BEFORE
    ``session.delete(source)``: ``Artist.aliases`` is a ``delete-orphan`` cascade,
    so any kept alias left pointing at the source would be deleted with it. Bulk
    UPDATE/DELETE keeps the move at the DB level (the cascade then lazy-loads an
    already-empty source alias set and removes nothing).
    """
    taken = {
        row[0]
        for row in session.execute(
            select(ArtistAlias.normalized_alias).where(
                ArtistAlias.artist_id == target.id
            )
        ).all()
    }
    taken.add(target.normalized_name)

    session.execute(
        delete(ArtistAlias)
        .where(
            ArtistAlias.artist_id == source_id,
            ArtistAlias.normalized_alias.in_(taken),
        )
        .execution_options(synchronize_session=False)
    )
    session.execute(
        update(ArtistAlias)
        .where(ArtistAlias.artist_id == source_id)
        .values(artist_id=target.id)
        .execution_options(synchronize_session=False)
    )


def _ensure_alias_sync(session, ArtistAlias, artist_id, alias_name, normalize):
    """Sync twin of ``artist_service._ensure_alias``.

    Adds an ``ArtistAlias`` for ``artist_id`` unless a row with the same
    ``normalized_alias`` already exists anywhere (the column is globally UNIQUE),
    or the name normalises to empty. No commit — the caller owns the transaction.
    """
    norm = normalize(alias_name)
    if not norm:
        return
    exists = session.execute(
        select(ArtistAlias).where(ArtistAlias.normalized_alias == norm)
    ).scalar_one_or_none()
    if exists is not None:
        return
    session.add(
        ArtistAlias(artist_id=artist_id, alias=alias_name, normalized_alias=norm)
    )


def merge_artist_into(session: Session, source_id: int, target_id: int) -> dict:
    """Fold artist ``source_id`` into ``target_id`` and delete the source.

    Reassigns every ``set_artists`` / ``catalog_artists`` link of the source to
    the target (conflict-aware on the composite PK), moves the source's aliases
    (honouring the UNIQUE ``normalized_alias``), preserves the source spelling as
    an alias of the target when it differs, then removes the source row. Mirrors
    the async merge in ``artist_service.link_to_deezer`` — but ALSO carries the
    source's existing aliases across (the async path only added the source name),
    since an accent-variant duplicate may already own useful aliases.

    Does NOT commit (the caller owns the transaction) and does NOT rewrite the
    target's ``normalized_name`` (the driver canonicalises the survivor once the
    source is gone, when there is no unique collision left). Returns a small
    report dict ``{"merged_source", "into", "name"}``.

    Raises ``ValueError`` if ``source_id == target_id`` (a self-merge would delete
    the only row — a caller bug, never a valid request) and ``LookupError`` if
    either artist is missing (mirrors ``artist_service`` raising ``LookupError``
    for a not-found artist).
    """
    from models import Artist, ArtistAlias, CatalogArtist, SetArtist
    from utils import normalize

    if source_id == target_id:
        raise ValueError(
            f"merge_artist_into: source and target are the same artist ({source_id})"
        )

    source = session.get(Artist, source_id)
    if source is None:
        raise LookupError(f"source artist {source_id} not found")
    target = session.get(Artist, target_id)
    if target is None:
        raise LookupError(f"target artist {target_id} not found")

    source_name = source.name

    # Reassign the association rows first (both are composite-PK tables keyed on
    # artist_id → conflict-aware, drop-then-move).
    _reassign_artist_links(session, SetArtist, SetArtist.set_id, source_id, target_id)
    _reassign_artist_links(
        session, CatalogArtist, CatalogArtist.catalog_id, source_id, target_id
    )

    # Move the source's aliases BEFORE deleting it (delete-orphan cascade), then
    # keep the source spelling itself as an alias so a lookup by the old
    # accent-sensitive name still resolves to the surviving artist.
    _move_aliases(session, ArtistAlias, source_id, target)
    if normalize(source_name) != normalize(target.name):
        _ensure_alias_sync(session, ArtistAlias, target.id, source_name, normalize)

    session.delete(source)
    session.flush()

    return {"merged_source": source_id, "into": target_id, "name": source_name}
