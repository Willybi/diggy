"""
Télécharge les covers Deezer et récupère les preview_url pour les entrées catalog.

Logique :
  - Pour chaque CatalogEntry ciblée :
      - Cherche un RadarTrack lié avec source='deezer'
      - Appelle GET https://api.deezer.com/track/{id} → cover_medium + preview
      - Upload cover dans MinIO 'catalog-artworks' (sauf si --preview-only)
      - Sauvegarde preview_url dans la table catalog

Usage (depuis le VPS) :
    docker compose exec api python scripts/fetch_catalog_artworks.py

Options :
    --limit N         Traite au maximum N entrées
    --force           Re-traite même si has_artwork=True
    --preview-only    Ne re-télécharge pas les covers, remplit seulement preview_url manquants
"""
import asyncio
import argparse
import os
import sys
import tempfile

import requests
import boto3
from botocore.client import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from models import CatalogEntry, RadarTrack

# — Config S3
MINIO_URL      = os.environ.get("MINIO_URL", "http://minio:9000")
MINIO_USER     = os.environ["MINIO_USER"]
MINIO_PASSWORD = os.environ["MINIO_PASSWORD"]
BUCKET         = "catalog-artworks"

s3 = boto3.client(
    "s3",
    endpoint_url=MINIO_URL,
    aws_access_key_id=MINIO_USER,
    aws_secret_access_key=MINIO_PASSWORD,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)

DEEZER_API = "https://api.deezer.com"
COVER_FIELD = "cover_medium"   # ~250×250px


def ensure_bucket():
    existing = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    if BUCKET not in existing:
        s3.create_bucket(Bucket=BUCKET)
        s3.put_bucket_policy(
            Bucket=BUCKET,
            Policy=(
                f'{{"Version":"2012-10-17","Statement":[{{"Effect":"Allow",'
                f'"Principal":"*","Action":"s3:GetObject",'
                f'"Resource":"arn:aws:s3:::{BUCKET}/*"}}]}}'
            ),
        )
        print(f"Bucket '{BUCKET}' créé.")


def fetch_deezer_track(deezer_track_id: str) -> dict | None:
    """Retourne {cover_url, preview_url} depuis l'API Deezer, ou None si erreur."""
    try:
        r = requests.get(f"{DEEZER_API}/track/{deezer_track_id}", timeout=10)
        r.raise_for_status()
        data = r.json()
        return {
            "cover_url":   data.get("album", {}).get(COVER_FIELD),
            "preview_url": data.get("preview"),
        }
    except Exception as e:
        print(f"  Deezer API error pour track {deezer_track_id}: {e}")
        return None


def upload_cover(img_bytes: bytes, catalog_id: int) -> None:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(img_bytes)
        tmp = f.name
    try:
        s3.upload_file(
            tmp, BUCKET, f"{catalog_id}.jpg",
            ExtraArgs={"ContentType": "image/jpeg"},
        )
    finally:
        os.unlink(tmp)


async def run(limit: int | None, force: bool, preview_only: bool):
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    if not preview_only:
        ensure_bucket()

    async with async_session() as db:
        q = select(CatalogEntry)
        if preview_only:
            # Cible uniquement les entrées sans preview_url
            q = q.where(CatalogEntry.preview_url.is_(None))
        elif not force:
            # Cible sans artwork OU sans preview
            q = q.where(
                (CatalogEntry.has_artwork == False) | CatalogEntry.preview_url.is_(None)
            )
        if limit:
            q = q.limit(limit)
        result = await db.execute(q)
        entries = result.scalars().all()

    print(f"{len(entries)} entrées à traiter.")

    ok = skipped = errors = 0

    async with async_session() as db:
        for entry in entries:
            # Trouve un radar_track Deezer lié
            r = await db.execute(
                select(RadarTrack.external_track_id)
                .where(RadarTrack.catalog_id == entry.id)
                .where(RadarTrack.source == "deezer")
                .limit(1)
            )
            row = r.first()
            if not row:
                skipped += 1
                continue

            deezer_id = row[0]
            dz = fetch_deezer_track(deezer_id)
            if not dz:
                errors += 1
                continue

            # Sauvegarde preview_url
            if dz["preview_url"]:
                entry.preview_url = dz["preview_url"]

            # Cover — skip si preview_only ou déjà présente
            if not preview_only and not entry.has_artwork and dz["cover_url"]:
                try:
                    img_resp = requests.get(dz["cover_url"], timeout=15)
                    img_resp.raise_for_status()
                    upload_cover(img_resp.content, entry.id)
                    entry.has_artwork = True
                except Exception as e:
                    print(f"  Cover error [{entry.id}]: {e}")

            db.add(entry)
            ok += 1

            if ok % 50 == 0:
                await db.commit()
                print(f"  {ok} entrées traitées…")

            await asyncio.sleep(0.15)

        await db.commit()

    print(f"\nTerminé — ok: {ok}, sans source Deezer: {skipped}, erreurs: {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--preview-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(limit=args.limit, force=args.force, preview_only=args.preview_only))
