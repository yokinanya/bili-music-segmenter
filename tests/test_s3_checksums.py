"""Verify real SDK upload requests without contacting an S3 service."""

import io

import pytest

from segment.music_agent.config import ApiConfig
from segment.music_agent.storage import create_storage


class RequestCaptured(Exception):
    pass


@pytest.mark.parametrize("operation", ["PutObject", "UploadPart"])
def test_upload_avoids_optional_streaming_checksum_trailers(operation):
    config = ApiConfig(
        api_key="test",
        base_url="https://example.com/v1",
        s3_access_key="test-id",
        s3_access_secret="test-secret",
        s3_endpoint="https://s3.example.com",
        s3_bucket="audio",
        s3_prefix="music",
        s3_region="us-east-1",
    )
    client = create_storage(config).client
    captured = []

    def capture(request, **kwargs):
        captured.append(request)
        raise RequestCaptured

    client.meta.events.register(f"before-send.s3.{operation}", capture)
    arguments = {"Bucket": "audio", "Key": "test.wav", "Body": io.BytesIO(b"audio")}
    if operation == "UploadPart":
        arguments = {**arguments, "UploadId": "test-upload", "PartNumber": 1}
    with pytest.raises(RequestCaptured):
        method = client.upload_part if operation == "UploadPart" else client.put_object
        method(**arguments)
    headers = {key.lower(): value for key, value in captured[0].headers.items()}
    assert headers.get("x-amz-content-sha256") != b"STREAMING-UNSIGNED-PAYLOAD-TRAILER"
    assert "x-amz-trailer" not in headers
    assert b"aws-chunked" not in headers.get("content-encoding", b"")
    assert headers["authorization"].startswith(b"AWS4-HMAC-SHA256 ")
