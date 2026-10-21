"""Serve the exported frontend bundle and read-only clip media.

The frontend is built from ``webui/`` with Next.js static export and copied to
``segment/webui_dist``. This module only reads files; nothing here can write to disk.
"""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

MIME_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".mp4": "video/mp4",
}
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._~-]+$")


def resolve_asset(root: Path, url_path: str) -> Path | None:
    """Map a URL path to a file inside ``root``; return None for traversal or missing files."""
    relative = url_path.lstrip("/")
    parts = [part for part in relative.split("/") if part]
    if not parts or any(part in {".", ".."} or not SAFE_SEGMENT.match(part) for part in parts):
        return None
    candidate = (root / "/".join(parts)).resolve()
    if root.resolve() not in candidate.parents or not candidate.is_file():
        return None
    return candidate


def content_type(path: Path) -> str:
    return MIME_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Return the inclusive byte range of a simple ``bytes=`` request, or None when unsupported."""
    if not header or not header.startswith("bytes="):
        return None
    spec = header.removeprefix("bytes=").split(",")[0].strip()
    try:
        start_text, _, end_text = spec.partition("-")
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
        else:
            # Suffix form: the last N bytes.
            suffix = int(end_text)
            start, end = max(0, size - suffix), size - 1
    except ValueError:
        return None
    end = min(end, size - 1)
    if start < 0 or start > end or start >= size:
        return None
    return start, end
