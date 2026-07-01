import os

import boto3
from botocore.client import Config

MINIO_URL = os.environ.get("MINIO_URL", "http://minio:9000")
MINIO_USER = os.environ["MINIO_USER"]
MINIO_PASSWORD = os.environ["MINIO_PASSWORD"]
BUCKET = "artworks"

s3 = boto3.client(
    "s3",
    endpoint_url=MINIO_URL,
    aws_access_key_id=MINIO_USER,
    aws_secret_access_key=MINIO_PASSWORD,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)


def ensure_bucket():
    existing = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    if BUCKET not in existing:
        s3.create_bucket(Bucket=BUCKET)
        s3.put_bucket_policy(
            Bucket=BUCKET,
            Policy=f'{{"Version":"2012-10-17","Statement":[{{"Effect":"Allow","Principal":"*","Action":"s3:GetObject","Resource":"arn:aws:s3:::{BUCKET}/*"}}]}}',
        )


def upload_artwork(file_path: str, object_key: str) -> str:
    """Upload un fichier image et retourne son URL publique."""
    s3.upload_file(
        file_path,
        BUCKET,
        object_key,
        ExtraArgs={"ContentType": "image/jpeg"},
    )
    return f"/storage/{BUCKET}/{object_key}"
