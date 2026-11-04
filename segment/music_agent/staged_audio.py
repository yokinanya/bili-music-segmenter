"""Prepare an audio window and reuse its retained S3 object."""

from pathlib import Path
from tempfile import TemporaryDirectory

from segment.music_agent.media import extract_wav
from segment.music_agent.runtime import CURRENT, fingerprint


def with_audio(media: Path, start: float, end: float, options: dict, call):
    scope = CURRENT.get()
    payload = {
        "source": scope.runtime.config["source_digest"] if scope else str(media),
        "start": start,
        "end": end,
        "prefix": options["prefix"],
    }
    if scope:

        def extract():
            return scope.runtime.local_cache.acquire(
                {"start": start, "end": end, "suffix": ".wav", "format": "pcm-s16le-24k-mono"},
                lambda destination: extract_wav(media, start, end, destination),
            )

        key = scope.runtime.audio_cache.acquire(payload, extract)
        return call(lambda: options["storage"].signed_url(key))
    # Standalone low-level API callers have no task owner; retain the object for their explicit cleanup.
    with TemporaryDirectory(prefix="music-audio-") as directory:
        wav = Path(directory) / "audio.wav"
        extract_wav(media, start, end, wav)
        key = "/".join(filter(None, (options["prefix"], "cache", fingerprint(payload) + ".wav")))
        options["storage"].upload(key, wav)
        return call(lambda: options["storage"].signed_url(key))
