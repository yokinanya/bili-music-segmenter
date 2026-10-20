"""S3-compatible private audio staging."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from segment.music_agent.config import ApiConfig
from segment.upload_progress import UploadReporter

SIGNED_URL_SECONDS = 3600
AUDIO_CONTENT_TYPE = "audio/wav"


class AudioStorage(Protocol):
    def upload(self, key: str, source: Path) -> None: ...

    def signed_url(self, key: str) -> str: ...

    def delete(self, key: str) -> None: ...


@dataclass(frozen=True)
class S3Storage:
    client: Any
    bucket: str

    def upload(self, key: str, source: Path) -> None:
        progress = UploadReporter(key, source.stat().st_size)
        progress.state("uploading")
        try:
            self.client.upload_file(
                str(source),
                self.bucket,
                key,
                ExtraArgs={"ContentType": AUDIO_CONTENT_TYPE},
                Callback=progress,
            )
        except Exception:
            progress.state("failed")
            raise
        progress.state("completed")

    def signed_url(self, key: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=SIGNED_URL_SECONDS,
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def create_storage(config: ApiConfig) -> S3Storage:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=config.s3_endpoint,
        region_name=config.s3_region,
        aws_access_key_id=config.s3_access_key,
        aws_secret_access_key=config.s3_access_secret,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": config.s3_addressing_style},
            user_agent=config.s3_user_agent,
        ),
    )
    return S3Storage(client, config.s3_bucket)
