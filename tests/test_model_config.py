import pytest

from segment.music_agent.config import load_config


@pytest.fixture
def model_env(monkeypatch):
    monkeypatch.setattr("segment.music_agent.config.load_dotenv", lambda *args: None)
    values = {
        "DASHSCOPE_API_KEY": "sk-test-key",
        "DASHSCOPE_BASE_URL": "https://model.example.com/compatible-mode/v1/",
        "S3_ACCESS_KEY_ID": "test-id",
        "S3_ACCESS_KEY_SECRET": "test-secret",
        "S3_ENDPOINT": "https://s3.example.com",
        "S3_BUCKET": "audio",
        "S3_REGION": "us-east-1",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_model_url_and_key(model_env):
    config = load_config()
    assert config.api_key == "sk-test-key"
    assert config.base_url == "https://model.example.com/compatible-mode/v1"


def test_swapped_model_credentials_explain_the_mistake(model_env, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "https://model.example.com/v1")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", "sk-test-key")
    with pytest.raises(ValueError, match="DASHSCOPE_BASE_URL.*DASHSCOPE_API_KEY.*填反") as error:
        load_config()
    assert "sk-test-key" not in str(error.value)


@pytest.mark.parametrize(
    "url", ["model.example.com/v1", "http://model.example.com/v1", "https://user:pass@model.example.com/v1"]
)
def test_model_url_still_requires_https_without_credentials(model_env, monkeypatch, url):
    monkeypatch.setenv("DASHSCOPE_BASE_URL", url)
    with pytest.raises(ValueError, match="DASHSCOPE_BASE_URL"):
        load_config()
