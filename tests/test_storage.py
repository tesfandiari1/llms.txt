"""Unit tests for Storage implementations - happy paths only."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("FIRECRAWL_API_KEY", "test-key")

from app.storage import LocalStorage, S3Storage


def test_local_storage_save():
    """LocalStorage.save creates file with content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = LocalStorage(Path(tmpdir))
        key = storage.save("test.txt", "Hello, World!")

        assert key == "test.txt"
        assert (Path(tmpdir) / "test.txt").exists()
        assert (Path(tmpdir) / "test.txt").read_text() == "Hello, World!"


def test_local_storage_read():
    """LocalStorage.read returns file content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = LocalStorage(Path(tmpdir))
        (Path(tmpdir) / "test.txt").write_text("Test content")

        content = storage.read("test.txt")

        assert content == "Test content"


def test_s3_storage_save():
    """S3Storage.save calls put_object with correct params."""
    with patch("app.storage.boto3.client") as mock_boto:
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3

        storage = S3Storage(
            bucket="test-bucket",
            endpoint_url="https://s3.example.com",
            access_key="key",
            secret_key="secret",
        )
        key = storage.save("job-123/llms.txt", "Content")

        assert key == "job-123/llms.txt"
        mock_s3.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="job-123/llms.txt",
            Body=b"Content",
            ContentType="text/plain; charset=utf-8",
        )


def test_s3_storage_read():
    """S3Storage.read returns decoded content."""
    with patch("app.storage.boto3.client") as mock_boto:
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3

        mock_body = MagicMock()
        mock_body.read.return_value = b"File content"
        mock_s3.get_object.return_value = {"Body": mock_body}

        storage = S3Storage(bucket="test-bucket")
        content = storage.read("test.txt")

        assert content == "File content"
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="test.txt"
        )
