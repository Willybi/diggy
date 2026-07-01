"""
Unified S3/MinIO image service.

Replaces the duplicated S3 code in storage.py and deezer_enrich.py.
Used by: admin, tracks, watchlist, trackid/importer, workers/tasks/*.
"""

import os
import tempfile

import boto3
import requests
from botocore.client import Config

MINIO_URL = os.environ.get("MINIO_URL", "http://minio:9000")
MINIO_USER = os.environ.get("MINIO_USER", "")
MINIO_PASSWORD = os.environ.get("MINIO_PASSWORD", "")

BUCKET_ARTWORKS = "artworks"
BUCKET_CATALOG = "catalog-artworks"
BUCKET_ARTIST = "artist-artworks"
BUCKET_PLAYLIST = "playlist-artworks"
BUCKET_SET = "set-artworks"


class ImageService:
    _client = None

    @classmethod
    def _get_s3(cls):
        if cls._client is None:
            cls._client = boto3.client(
                "s3",
                endpoint_url=MINIO_URL,
                aws_access_key_id=MINIO_USER,
                aws_secret_access_key=MINIO_PASSWORD,
                config=Config(signature_version="s3v4"),
                region_name="us-east-1",
            )
        return cls._client

    @classmethod
    def ensure_bucket(cls, bucket: str) -> None:
        s3 = cls._get_s3()
        existing = [b["Name"] for b in s3.list_buckets()["Buckets"]]
        if bucket not in existing:
            s3.create_bucket(Bucket=bucket)
            s3.put_bucket_policy(
                Bucket=bucket,
                Policy=(
                    f'{{"Version":"2012-10-17","Statement":[{{"Effect":"Allow",'
                    f'"Principal":"*","Action":"s3:GetObject",'
                    f'"Resource":"arn:aws:s3:::{bucket}/*"}}]}}'
                ),
            )

    @classmethod
    def upload_bytes(cls, data: bytes, bucket: str, key: str) -> bool:
        """Upload raw image bytes. Returns True on success."""
        if not data or len(data) < 1000:
            return False
        s3 = cls._get_s3()
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(data)
                tmp = f.name
            try:
                s3.upload_file(tmp, bucket, key, ExtraArgs={"ContentType": "image/jpeg"})
            finally:
                os.unlink(tmp)
            return True
        except Exception:
            return False

    @classmethod
    def upload_from_url(cls, url: str, bucket: str, key: str) -> bool:
        """Download image from URL and upload. Returns True on success."""
        if not url:
            return False
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            return cls.upload_bytes(resp.content, bucket, key)
        except Exception:
            return False

    @classmethod
    def upload_file(cls, file_path: str, bucket: str, key: str) -> str:
        """Upload a local file. Returns public URL."""
        s3 = cls._get_s3()
        s3.upload_file(
            file_path,
            bucket,
            key,
            ExtraArgs={"ContentType": "image/jpeg"},
        )
        return f"/storage/{bucket}/{key}"

    @classmethod
    async def fetch_playlist_artworks(cls, db, playlist_ids: list[int] | None = None) -> dict:
        """Fetch Deezer artworks for watched playlists missing artwork."""
        from models import WatchedEntity
        from sqlalchemy import select

        query = select(WatchedEntity).where(
            WatchedEntity.has_artwork.is_(False),
            WatchedEntity.source == "deezer",
        )
        if playlist_ids:
            query = query.where(WatchedEntity.id.in_(playlist_ids))

        result = await db.execute(query)
        playlists = result.scalars().all()

        if not playlists:
            return {"fetched": 0, "failed": 0, "total": 0}

        cls.ensure_bucket(BUCKET_PLAYLIST)

        fetched = 0
        failed = 0
        for pl in playlists:
            try:
                resp = requests.get(
                    f"https://api.deezer.com/playlist/{pl.external_id}", timeout=5
                )
                data = resp.json()
                pic_url = (
                    data.get("picture_xl")
                    or data.get("picture_big")
                    or data.get("picture_medium")
                )
                if pic_url and cls.upload_from_url(pic_url, BUCKET_PLAYLIST, f"{pl.id}.jpg"):
                    pl.has_artwork = True
                    fetched += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        return {"fetched": fetched, "failed": failed, "total": len(playlists)}
