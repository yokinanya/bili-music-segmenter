from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from botocore.stub import Stubber

from segment.music_agent import detection, models
from segment.music_agent.config import ApiConfig, load_config
from segment.music_agent.storage import SIGNED_URL_SECONDS, S3Storage, create_storage


@pytest.fixture
def config_env(monkeypatch):
    monkeypatch.setattr("segment.music_agent.config.load_dotenv", lambda *args: None)
    values = {
        "DASHSCOPE_API_KEY": "test-key",
        "DASHSCOPE_BASE_URL": "https://example.com/v1",
        "S3_ACCESS_KEY_ID": "test-id",
        "S3_ACCESS_KEY_SECRET": "test-secret",
        "S3_ENDPOINT": "https://s3.example.com",
        "S3_BUCKET": "audio",
        "S3_REGION": "us-east-1",
        "S3_PREFIX": "music-agent",
        "S3_ADDRESSING_STYLE": "path",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


@pytest.mark.parametrize(
    "endpoint,expected",
    [
        ("s3.example.com", "https://s3.example.com"),
        ("s3.example.com:9000/", "https://s3.example.com:9000"),
        ("https://s3.example.com/", "https://s3.example.com"),
        ("http://localhost:9000", "http://localhost:9000"),
    ],
)
def test_s3_endpoint_optional_scheme(config_env, monkeypatch, endpoint, expected):
    monkeypatch.setenv("S3_ENDPOINT", endpoint)
    assert load_config().s3_endpoint == expected


def test_config_loads_s3(config_env, monkeypatch):
    config = load_config()
    assert config.s3_region == "us-east-1"
    assert config.s3_endpoint == "https://s3.example.com"
    assert config.s3_addressing_style == "path"
    monkeypatch.setenv("S3_PREFIX", "")
    assert load_config().s3_prefix == ""
    monkeypatch.delenv("S3_REGION")
    with pytest.raises(ValueError, match="S3_REGION"):
        load_config()


@pytest.mark.parametrize(
    "name,value",
    [
        ("S3_ENDPOINT", "ftp://example.com"),
        ("S3_ENDPOINT", "https://user:pass@example.com"),
        ("S3_ENDPOINT", "https://example.com?key=secret"),
        ("S3_ADDRESSING_STYLE", "invalid"),
    ],
)
def test_invalid_s3_config(config_env, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        load_config()


@pytest.mark.parametrize("value", [None, "", "custom-client/1.0"])
def test_s3_user_agent(config_env, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("S3_USER_AGENT", raising=False)
    else:
        monkeypatch.setenv("S3_USER_AGENT", value)
    config = load_config()
    assert config.s3_user_agent == (value or None)
    storage = create_storage(config)
    client = storage.client
    operation = client.meta.service_model.operation_model("DeleteObject")
    request_dict = client._convert_to_request_dict(
        {"Bucket": "audio", "Key": "test.wav"},
        operation,
        client.meta.endpoint_url,
    )
    request = client._endpoint.create_request(request_dict, operation)
    user_agent = request.headers["User-Agent"].decode()
    if value:
        assert user_agent.startswith(value)
    else:
        assert "Boto3/" in user_agent


@pytest.mark.parametrize("style", ["path", "virtual"])
def test_real_sdk_presigned_url_and_delete(style):
    config = ApiConfig(
        "test",
        "https://example.com/v1",
        "id",
        "secret",
        "https://s3.example.com",
        "audio",
        "music",
        "us-east-1",
        style,
    )
    storage = create_storage(config)
    url = urlsplit(storage.signed_url("music/中文.wav"))
    assert url.hostname == ("s3.example.com" if style == "path" else "audio.s3.example.com")
    query = parse_qs(url.query)
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-Expires"] == [str(SIGNED_URL_SECONDS)]
    assert "us-east-1/s3/aws4_request" in query["X-Amz-Credential"][0]
    with Stubber(storage.client) as stubber:
        stubber.add_response("delete_object", {}, {"Bucket": "audio", "Key": "music/中文.wav"})
        storage.delete("music/中文.wav")
        stubber.assert_no_pending_responses()


def test_upload_arguments(tmp_path):
    client = Mock()
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    S3Storage(client, "audio").upload("music/input.wav", source)
    assert client.upload_file.call_args.args == (str(source), "audio", "music/input.wav")
    assert client.upload_file.call_args.kwargs["ExtraArgs"] == {"ContentType": "audio/wav"}
    assert callable(client.upload_file.call_args.kwargs["Callback"])


def staging_case(monkeypatch, stage):
    storage = Mock()
    storage.signed_url.return_value = "https://example.com/audio"
    monkeypatch.setattr(models, "extract_wav", lambda *args: None)
    monkeypatch.setattr(detection, "extract_wav", lambda *args: None)
    monkeypatch.setattr(detection, "media_duration", lambda _: 60)
    response = {"data": {"segments": []}, "usage": None}
    model_call = Mock(return_value=response)
    monkeypatch.setattr(models, "audio_model_call", model_call)
    monkeypatch.setattr(detection, "audio_model_call", model_call)

    def invoke():
        if stage == "scan":
            return detection.scan_candidates(
                Path("input.mp4"),
                None,
                storage,
                chunk_seconds=60,
                chunk_context=0,
                s3_prefix="music",
                model="test",
            )
        return models.call_with_storage(
            Path("input.mp4"),
            0,
            60,
            None,
            storage,
            model="test",
            prompt="test",
            s3_prefix="music",
        )

    return SimpleNamespace(storage=storage, model_call=model_call, invoke=invoke)


@pytest.mark.parametrize("stage", ["scan", "boundary"])
@pytest.mark.parametrize("failure", [None, "upload", "signed_url", "model", "delete"])
def test_staging_cleanup_and_errors(monkeypatch, stage, failure):
    case = staging_case(monkeypatch, stage)
    if failure:
        target = case.model_call if failure == "model" else getattr(case.storage, failure)
        target.side_effect = RuntimeError(failure)
        with pytest.raises(RuntimeError, match=failure):
            case.invoke()
    else:
        case.invoke()
    key = case.storage.upload.call_args.args[0]
    assert key.startswith("music/")
    if failure == "upload":
        case.storage.delete.assert_not_called()
    else:
        case.storage.delete.assert_called_once_with(key)
