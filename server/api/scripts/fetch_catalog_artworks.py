"""
Télécharge les covers Deezer pour les entrées catalog sans artwork.

Logique :
  - Pour chaque CatalogEntry où has_artwork=False :
      - Cherche un RadarTrack lié avec source='deezer'
      - Appelle GET https://api.deezer.com/track/{external_track_id}
      - Télécharge album.cover_medium (~250x250)
      - Upload dans le bucket MinIO 'catalog-artworks' sous {catalog_id}.jpg
      - Met has_artwork=True dans la table catalog

Usage (depuis le VPS) :
    docker compose exec api python scripts/fetch_catalog_artworks.py

Options :
    --limit N    Traite au maximum N entrées (utile pour tester)
    --force      Re-télécharge même si has_artwork=True
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


def fetch_cover_url(deezer_track_id: str) -> str | None:
    try:
        r = requests.get(f"{DEEZER_API}/track/{deezer_track_id}", timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("album", {}).get(COVER_FIELD)
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


async def run(limit: int | None, force: bool):
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    ensure_bucket()

    async with async_session() as db:
        # Entrées catalog sans artwork (ou toutes si --force)
        q = select(CatalogEntry)
        if not force:
            q = q.where(CatalogEntry.has_artwork == False)
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
            cover_url = fetch_cover_url(deezer_id)
            if not cover_url:
                errors += 1
                continue

            # Télécharge la cover
            try:
                img_resp = requests.get(cover_url, timeout=15)
                img_resp.raise_for_status()
                img_bytes = img_resp.content
            except Exception as e:
                print(f"  Download error [{entry.id}] {entry.artist} — {entry.title}: {e}")
                errors += 1
                continue

            # Upload S3
            try:
                upload_cover(img_bytes, entry.id)
            except Exception as e:
                print(f"  S3 upload error [{entry.id}]: {e}")
                errors += 1
                continue

            # Update DB
            entry.has_artwork = True
            db.add(entry)
            ok += 1

            if ok % 50 == 0:
                await db.commit()
                print(f"  {ok} covers uploadées…")

            # Petit délai pour ne pas hammerer l'API Deezer
            await asyncio.sleep(0.15)

        await db.commit()

    print(f"\nTerminé — ok: {ok}, sans source Deezer: {skipped}, erreurs: {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(limit=args.limit, force=args.force))
