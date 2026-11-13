import pytest

from segment.music_agent.json_response import parse_json


def test_plain_and_fenced_json():
    assert parse_json('{"a": 1}') == {"a": 1}
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        "[1, 2]",
        '```json\n{"a": 1}',
        '```json\n{"a": 1}\n```\ntrailing',
    ],
)
def test_invalid_json_has_explicit_error(content):
    with pytest.raises(ValueError):
        parse_json(content)
