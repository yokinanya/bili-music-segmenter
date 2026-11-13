import pytest

from segment.music_agent import gemini
from segment.music_agent.config import load_config


@pytest.fixture
def model_env(monkeypatch):
    monkeypatch.setattr("segment.music_agent.config.load_dotenv", lambda *args: None)
    values = {
        "GEMINI_API_KEY": "test-key",
        "S3_ACCESS_KEY_ID": "test-id",
        "S3_ACCESS_KEY_SECRET": "test-secret",
        "S3_ENDPOINT": "https://s3.example.com",
        "S3_BUCKET": "audio",
        "S3_REGION": "us-east-1",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_gemini_key_and_defaults(model_env, monkeypatch):
    monkeypatch.delenv("GEMINI_PROXY", raising=False)
    monkeypatch.delenv("GEMINI_AUDIO_MODEL", raising=False)
    config = load_config()
    assert config.gemini.api_key == "test-key"
    assert config.gemini.proxy is None
    assert config.gemini.model == "gemini-4-hydrogen"


def test_gemini_proxy_and_model_override(model_env, monkeypatch):
    monkeypatch.setenv("GEMINI_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("GEMINI_AUDIO_MODEL", "gemini-4-argon")
    config = load_config()
    assert config.gemini.proxy == "http://127.0.0.1:7890"
    assert config.gemini.model == "gemini-4-argon"


def test_proxy_is_installed_on_the_http_client():
    """google-genai 没有 proxy 参数，必须通过自建 httpx 客户端注入。"""
    client = gemini._http_client("socks5://127.0.0.1:1080")
    try:
        assert client._mounts
    finally:
        client.close()


def test_missing_gemini_key_is_reported(model_env, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        load_config()


def test_proxy_requires_scheme(model_env, monkeypatch):
    monkeypatch.setenv("GEMINI_PROXY", "127.0.0.1:7890")
    with pytest.raises(ValueError, match="GEMINI_PROXY"):
        load_config()
