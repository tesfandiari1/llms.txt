"""File storage abstraction - local for dev, S3 for prod."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings

__all__ = ["LocalStorage", "S3Storage", "Storage", "get_storage"]

logger = logging.getLogger(__name__)


class Storage(ABC):
    @abstractmethod
    def save(self, key: str, content: str) -> str:
        """Save content and return a key for retrieval."""
        ...

    @abstractmethod
    def get_url(self, key: str) -> str:
        """Get a download URL for the given key."""
        ...

    @abstractmethod
    def read(self, key: str) -> str | None:
        """Read content by key, return None if not found."""
        ...

    def save_multiple(self, files: dict[str, str]) -> dict[str, str]:
        """
        Save multiple files and return dict of {name: key}.

        Args:
            files: Dict mapping filename to content, e.g.
                   {"uuid/llms.txt": "content", "uuid/llms-ctx.txt": "content"}

        Returns:
            Dict mapping the same filenames to storage keys
        """
        return {name: self.save(name, content) for name, content in files.items()}


class LocalStorage(Storage):
    """Local filesystem storage for development."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, key: str) -> Path:
        """Validate key doesn't escape base_dir via path traversal."""
        path = (self.base_dir / key).resolve()
        base = self.base_dir.resolve()
        if not path.is_relative_to(base):
            msg = f"Invalid key: {key}"
            raise ValueError(msg)
        return path

    def save(self, key: str, content: str) -> str:
        path = self._safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return key  # Return key, not path

    def get_url(self, key: str) -> str:
        # For local, URL is just the API download endpoint
        return f"/api/files/{key}"

    def read(self, key: str) -> str | None:
        path = self._safe_path(key)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None


class S3Storage(Storage):
    """S3-compatible storage for production (AWS S3, Cloudflare R2)."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ):
        self.bucket = bucket
        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )

    def save(self, key: str, content: str) -> str:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        logger.info(f"Saved file to S3: {key}")
        return key

    def read(self, key: str) -> str | None:
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read().decode("utf-8")
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    def get_url(self, key: str) -> str:
        # Generate presigned URL valid for 1 hour
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=3600,
        )


def get_storage() -> Storage:
    """Factory function - swap implementation via config."""
    if settings.storage_type == "s3":
        if not settings.s3_bucket:
            msg = "S3_BUCKET is required when STORAGE_TYPE=s3"
            raise ValueError(msg)
        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
        )
    return LocalStorage(Path(settings.outputs_dir))

