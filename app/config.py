import os

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    anthropic_api_key: str
    firecrawl_api_key: str
    outputs_dir: str = "/outputs"

    # LLM model configuration
    anthropic_model: str = "claude-haiku-4-5"  # For per-page summaries
    anthropic_model_advanced: str = "claude-sonnet-4-5"  # For site summaries

    # CORS configuration
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Storage configuration
    storage_type: str = "local"  # "local" or "s3"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None  # For Cloudflare R2
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def validate_railway_storage(self):
        """Fail fast if using local storage on Railway."""
        if self.storage_type == "local" and os.environ.get("RAILWAY_ENVIRONMENT"):
            msg = (
                "Cannot use local storage on Railway (ephemeral filesystem). "
                "Set STORAGE_TYPE=s3 and configure S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY."
            )
            raise ValueError(msg)
        return self


settings = Settings()
