"""
Unified S3/MinIO image service.

Single entry point for artwork storage: bucket creation (public-read policy),
uploads from bytes/URL/file, object copy, and playlist artwork fetching.
Used by routers, services, trackid/importer, scripts and workers/tasks/*.
"""

import os
import tempfile

import boto3
import requests
from botocore.client import Config
from starlette.concurrency import run_in_threadpool

MINIO_URL = os.environ.get("MINIO_URL", "http://minio:9000")
MINIO_USER = os.environ.get("MINIO_USER", "")
MINIO_PASSWORD = os.environ.get("MINIO_PASSWORD", "")

BUCKET_ARTWORKS = "artworks"
BUCKET_CATALOG = "catalog-artworks"
BUCKET_ARTIST = "artist-artworks"
BUCKET_PLAYLIST = "playlist-artworks"
BUCKET_SET = "set-artworks"
BUCKET_ALBUM = "album-artworks"


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
    def upload_fileobj(
        cls,
        fileobj,
        bucket: str,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Upload a file-like object (blocking boto3 call).

        Public wrapper over the boto3 client so callers never reach for the
        private `_get_s3()`; run it via `run_in_threadpool` from async code.
        """
        cls._get_s3().upload_fileobj(
            fileobj, bucket, key, ExtraArgs={"ContentType": content_type}
        )

    @classmethod
    def copy_object(cls, bucket: str, src_key: str, dst_key: str) -> bool:
        """Copy an object within the same bucket. Returns True on success."""
        if src_key == dst_key:
            return True
        try:
            cls._get_s3().copy_object(
                Bucket=bucket,
                CopySource={"Bucket": bucket, "Key": src_key},
                Key=dst_key,
            )
            return True
        except Exception:
            return False

    @classmethod
    def _fetch_playlist_artwork(cls, external_id: str, playlist_id: int) -> bool:
        """Download a playlist's Deezer artwork and upload to MinIO (blocking).

        Network (requests) + boto3 are synchronous, so this runs off the event
        loop via `run_in_threadpool`. Returns True on a successful fetch+upload,
        False on any network/upload failure (an error is a non-fetch, not a raise).
        """
        try:
            resp = requests.get(
                f"https://api.deezer.com/playlist/{external_id}", timeout=5
            )
            data = resp.json()
            pic_url = (
                data.get("picture_xl")
                or data.get("picture_big")
                or data.get("picture_medium")
            )
            return bool(
                pic_url
                and cls.upload_from_url(pic_url, BUCKET_PLAYLIST, f"{playlist_id}.jpg")
            )
        except Exception:
            return False

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

        await run_in_threadpool(cls.ensure_bucket, BUCKET_PLAYLIST)

        fetched = 0
        failed = 0
        for pl in playlists:
            if await run_in_threadpool(
                cls._fetch_playlist_artwork, pl.external_id, pl.id
            ):
                pl.has_artwork = True
                fetched += 1
            else:
                failed += 1

        # Persist the has_artwork flags: get_db does not commit on exit, so
        # without this the mutations are dropped and every run re-downloads the
        # same playlists (the has_artwork.is_(False) filter never empties).
        # Mirrors the unit path watchlist_service.fetch_artwork.
        await db.commit()
        return {"fetched": fetched, "failed": failed, "total": len(playlists)}
