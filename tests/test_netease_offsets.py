"""网易云识曲按多采样点投票：起点不同可能识别出不同录音，用多数决取一致结果。"""

import pytest

from segment import netease


def test_offsets_start_at_clip_head_and_drop_out_of_range():
    # 从切片开头取样；不足 200 秒时 200 秒外的起点会被丢弃。
    assert netease.sample_offsets(206) == (6, 12, 20, 30)
    assert netease.sample_offsets(24) == (6, 12, 20)


def test_slice_shorter_than_one_window_is_rejected():
    assert netease.sample_offsets(2) == ()


def test_same_song_from_all_offsets_returns_match(monkeypatch):
    seen = []

    def fake_match(audio_fp, *, duration, cookie, timeout):
        seen.append(audio_fp)
        return {"name": "天黑黑", "artist": "孙燕姿"}

    monkeypatch.setattr(netease, "generate_audio_fp", lambda file, offset: f"fp-{offset}")
    monkeypatch.setattr(netease, "_post_audio_match", fake_match)
    match = netease._recognize_with_offsets("a.mp3", duration=200, cookie="", offsets=netease.AFP_OFFSETS, timeout=5)

    assert match == {"name": "天黑黑", "artist": "孙燕姿"}
    assert len(seen) == 4


def test_majority_wins_over_minority_noise(monkeypatch):
    """实测：中段采样会混入别的音频，7:1 时应采用多数结果而不是报冲突。"""

    def fake_match(audio_fp, *, duration, cookie, timeout):
        return (
            {"name": "定格的瞬间", "artist": "源泽"}
            if audio_fp.endswith("-88")
            else {"name": "唯一", "artist": "G.E.M.邓紫棋"}
        )

    monkeypatch.setattr(netease, "generate_audio_fp", lambda file, offset: f"fp-{offset}")
    monkeypatch.setattr(netease, "_post_audio_match", fake_match)
    points = (88, 98, 106, 112, 124, 130, 138, 148)
    match = netease._recognize_with_offsets("a.mp3", duration=235, cookie="", offsets=points, timeout=5)
    assert match["name"] == "唯一"


def test_versions_of_same_song_share_one_vote(monkeypatch):
    """cover/伴奏/纯享版属于同一作品，不能拆成不同票导致平票。"""
    versions = ["爱你", "爱你（cover王心凌）", "爱你 (伴奏)", "爱你【纯享版】"]

    def fake_match(audio_fp, *, duration, cookie, timeout):
        index = int(audio_fp.split("-")[-1]) % len(versions)
        return {"name": versions[index], "artist": "某人"}

    monkeypatch.setattr(netease, "generate_audio_fp", lambda file, offset: f"fp-{offset}")
    monkeypatch.setattr(netease, "_post_audio_match", fake_match)
    match = netease._recognize_with_offsets("a.mp3", duration=200, cookie="", offsets=(6, 12, 20, 30), timeout=5)
    assert match["name"].startswith("爱你")
    artist = {"artist": "某人"}
    assert netease.netease_match_key({"name": "爱你【纯享版】", **artist}) == netease.netease_match_key(
        {"name": "爱你", **artist}
    )
    # 歌名主体不同就必须是不同票，否则不同的歌会被误并。
    assert netease.netease_match_key({"name": "空空（温柔版）", **artist}) != netease.netease_match_key(
        {"name": "定格的瞬间", **artist}
    )


def test_tie_between_two_songs_raises_disagreement(monkeypatch):
    def fake_match(audio_fp, *, duration, cookie, timeout):
        offset = int(audio_fp.split("-")[-1])
        return {"name": "别的歌", "artist": "别人"} if offset < 20 else {"name": "天黑黑", "artist": "孙燕姿"}

    monkeypatch.setattr(netease, "generate_audio_fp", lambda file, offset: f"fp-{offset}")
    monkeypatch.setattr(netease, "_post_audio_match", fake_match)
    with pytest.raises(netease.NetEaseDisagreement):
        netease._recognize_with_offsets("a.mp3", duration=200, cookie="", offsets=(6, 12, 20, 30), timeout=5)


def test_partial_misses_do_not_block_a_match(monkeypatch):
    def fake_match(audio_fp, *, duration, cookie, timeout):
        if audio_fp.endswith("-6"):
            raise netease.NetEaseNoMatch("noMatchReason=1")
        return {"name": "天黑黑", "artist": "孙燕姿"}

    monkeypatch.setattr(netease, "generate_audio_fp", lambda file, offset: f"fp-{offset}")
    monkeypatch.setattr(netease, "_post_audio_match", fake_match)
    match = netease._recognize_with_offsets("a.mp3", duration=200, cookie="", offsets=netease.AFP_OFFSETS, timeout=5)
    assert match["name"] == "天黑黑"


def test_all_misses_still_reports_no_match(monkeypatch):
    def fake_match(*args, **kwargs):
        raise netease.NetEaseNoMatch("noMatchReason=1, queryId=x")

    monkeypatch.setattr(netease, "generate_audio_fp", lambda file, offset: f"fp-{offset}")
    monkeypatch.setattr(netease, "_post_audio_match", fake_match)
    with pytest.raises(netease.NetEaseNoMatch, match="noMatchReason"):
        netease._recognize_with_offsets("a.mp3", duration=200, cookie="", offsets=netease.AFP_OFFSETS, timeout=5)


def test_disagreement_maps_to_conflict_and_blocks_auto_title():
    from segment.music_agent import recognition

    groups = [(6, "别的歌", "别人"), (12, "天黑黑", "孙燕姿")]
    result = recognition.netease_outcome(netease.NetEaseDisagreement(groups))
    assert result["status"] == "conflict"
    assert result["samples"] == [[6, "别的歌", "别人"], [12, "天黑黑", "孙燕姿"]]
    assert recognition.deterministic_title_choice({"netease": result}) == ("", "", "conflict")


def test_total_deadline_stops_remaining_samples(monkeypatch):
    """单点超时不是总时限：慢网络下四个采样点不能累计等四倍超时。"""
    clock = {"now": 0.0}
    seen = []

    def fake_match(audio_fp, *, duration, cookie, timeout):
        seen.append(audio_fp)
        clock["now"] += 50.0
        return {"name": "天黑黑", "artist": "孙燕姿"}

    monkeypatch.setattr(netease, "generate_audio_fp", lambda file, offset: f"fp-{offset}")
    monkeypatch.setattr(netease, "_post_audio_match", fake_match)
    monkeypatch.setattr(netease.time, "monotonic", lambda: clock["now"])

    match = netease._recognize_with_offsets(
        "a.mp3", duration=200, cookie="", offsets=netease.AFP_OFFSETS, timeout=60, deadline=120.0
    )
    # 每点耗时 50 秒：第三个点开始时已用 100 秒，第四个点开始时 150 秒超过 120 秒时限，被跳过。
    assert len(seen) == 3
    assert match["name"] == "天黑黑"


def test_total_deadline_without_any_match_reports_no_match(monkeypatch):
    clock = {"now": 0.0}

    def slow(*args, **kwargs):
        clock["now"] += 200.0
        raise netease.NetEaseNoMatch("timeout")

    monkeypatch.setattr(netease, "generate_audio_fp", lambda file, offset: "fp")
    monkeypatch.setattr(netease, "_post_audio_match", slow)
    monkeypatch.setattr(netease.time, "monotonic", lambda: clock["now"])

    with pytest.raises(netease.NetEaseNoMatch):
        netease._recognize_with_offsets(
            "a.mp3", duration=200, cookie="", offsets=netease.AFP_OFFSETS, timeout=60, deadline=120.0
        )


def test_single_sample_timeout_is_clipped_to_remaining_deadline(monkeypatch):
    clock = {"now": 0.0}
    limits = []

    def fake_match(audio_fp, *, duration, cookie, timeout):
        limits.append(timeout)
        clock["now"] += 50.0
        return {"name": "天黑黑", "artist": "孙燕姿"}

    monkeypatch.setattr(netease, "generate_audio_fp", lambda file, offset: f"fp-{offset}")
    monkeypatch.setattr(netease, "_post_audio_match", fake_match)
    monkeypatch.setattr(netease.time, "monotonic", lambda: clock["now"])

    netease._recognize_with_offsets(
        "a.mp3", duration=200, cookie="", offsets=netease.AFP_OFFSETS, timeout=60, deadline=120.0
    )
    # 第一点 60 秒，第二点剩余 60 秒，第三点只剩 20 秒。
    assert limits == [60, 60, 20]
