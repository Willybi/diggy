"""Tests for services/image_service.py — pure unit tests (no DB needed)."""
from unittest.mock import MagicMock, patch

import pytest

from services.image_service import BUCKET_ARTWORKS, BUCKET_CATALOG, ImageService


class _FakeClientError(Exception):
    """Faithful stand-in for botocore.exceptions.ClientError.

    The api test harness stubs `botocore` in sys.modules (see conftest) without
    `botocore.exceptions`, so the real ClientError isn't importable here. This
    mirrors the only attribute ensure_bucket relies on: `.response["Error"]["Code"]`.
    """

    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class TestUploadFromUrl:
    def test_returns_false_for_empty_string(self):
        assert ImageService.upload_from_url("", "bucket", "key.jpg") is False

    def test_returns_false_for_none(self):
        assert ImageService.upload_from_url(None, "bucket", "key.jpg") is False

    @patch("services.image_service.requests.get")
    def test_returns_false_for_small_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = b"tiny"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        assert ImageService.upload_from_url("http://img.jpg", "bucket", "key.jpg") is False

    @patch.object(ImageService, "upload_bytes", return_value=True)
    @patch("services.image_service.requests.get")
    def test_returns_true_for_valid_image(self, mock_get, mock_upload):
        content = b"x" * 2000
        mock_resp = MagicMock()
        mock_resp.content = content
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = ImageService.upload_from_url("http://img.jpg", "bucket", "key.jpg")
        assert result is True
        mock_upload.assert_called_once_with(content, "bucket", "key.jpg")

    @patch("services.image_service.requests.get", side_effect=Exception("network error"))
    def test_returns_false_on_request_exception(self, _mock_get):
        assert ImageService.upload_from_url("http://img.jpg", "bucket", "key.jpg") is False


class TestUploadBytes:
    def test_returns_false_for_empty_bytes(self):
        assert ImageService.upload_bytes(b"", "bucket", "key.jpg") is False

    def test_returns_false_for_small_bytes(self):
        assert ImageService.upload_bytes(b"small", "bucket", "key.jpg") is False

    @patch("services.image_service.os.unlink")
    @patch("services.image_service.tempfile.NamedTemporaryFile")
    def test_uploads_valid_bytes(self, mock_tmpfile, mock_unlink):
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.jpg"
        mock_file.__enter__ = lambda s: mock_file
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_tmpfile.return_value = mock_file

        mock_s3 = MagicMock()
        ImageService._client = mock_s3

        try:
            result = ImageService.upload_bytes(b"x" * 2000, "bucket", "key.jpg")
            assert result is True
            mock_s3.upload_file.assert_called_once()
        finally:
            ImageService._client = None


class TestUploadFileobj:
    def test_delegates_to_s3_with_content_type(self):
        mock_s3 = MagicMock()
        ImageService._client = mock_s3
        try:
            fileobj = object()
            ImageService.upload_fileobj(fileobj, "bucket", "key.xml", "application/xml")
            mock_s3.upload_fileobj.assert_called_once_with(
                fileobj,
                "bucket",
                "key.xml",
                ExtraArgs={"ContentType": "application/xml"},
            )
        finally:
            ImageService._client = None

    def test_defaults_content_type(self):
        mock_s3 = MagicMock()
        ImageService._client = mock_s3
        try:
            ImageService.upload_fileobj(object(), "bucket", "key")
            _, kwargs = mock_s3.upload_fileobj.call_args
            assert kwargs["ExtraArgs"] == {"ContentType": "application/octet-stream"}
        finally:
            ImageService._client = None


class TestEnsureBucket:
    @staticmethod
    def _s3_missing_bucket():
        s3 = MagicMock()
        s3.list_buckets.return_value = {"Buckets": [{"Name": "other-bucket"}]}
        return s3

    def test_swallows_already_owned_race(self):
        s3 = self._s3_missing_bucket()
        s3.create_bucket.side_effect = _FakeClientError("BucketAlreadyOwnedByYou")
        ImageService._client = s3
        try:
            ImageService.ensure_bucket("artworks")
            s3.put_bucket_policy.assert_called_once()
        finally:
            ImageService._client = None

    def test_swallows_already_exists_race(self):
        s3 = self._s3_missing_bucket()
        s3.create_bucket.side_effect = _FakeClientError("BucketAlreadyExists")
        ImageService._client = s3
        try:
            ImageService.ensure_bucket("artworks")
            s3.put_bucket_policy.assert_called_once()
        finally:
            ImageService._client = None

    def test_propagates_other_client_error(self):
        s3 = self._s3_missing_bucket()
        s3.create_bucket.side_effect = _FakeClientError("AccessDenied")
        ImageService._client = s3
        try:
            with pytest.raises(_FakeClientError):
                ImageService.ensure_bucket("artworks")
            s3.put_bucket_policy.assert_not_called()
        finally:
            ImageService._client = None


class TestConstants:
    def test_bucket_names(self):
        assert BUCKET_ARTWORKS == "artworks"
        assert BUCKET_CATALOG == "catalog-artworks"
