"""Local HTTP transport, authentication, static assets and ranged downloads."""

from __future__ import annotations

import json
import logging
import secrets
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from segment.webui_static import content_type, parse_range, resolve_asset

HOST = "127.0.0.1"
MAX_BODY_BYTES = 64 * 1024
COPY_BYTES = 256 * 1024
LOGGER = logging.getLogger(__name__)


class WorkspaceHTTP(BaseHTTPRequestHandler):
    server_version = "BiliMusicSegmenter"
    sys_version = ""

    def _authorized(self) -> bool:
        port = self.server.server_port
        if self.headers.get("Host") not in {f"{HOST}:{port}", f"localhost:{port}"}:
            self._json(403, {"error": "请使用启动时显示的本机地址访问"})
            return False
        route = urlsplit(self.path).path
        if not route.startswith("/api/"):
            return True
        supplied = self.headers.get("X-WebUI-Token", "")
        if route.endswith("/archive") or "/clip/" in route or "/manifest/" in route:
            supplied = supplied or self._query("token")
        if secrets.compare_digest(supplied, self.token):
            return True
        self._json(403, {"error": "访问令牌无效，请使用服务启动时显示的地址"})
        return False

    def _query(self, name: str) -> str:
        values = parse_qs(urlsplit(self.path).query).get(name, [])
        return values[0] if len(values) == 1 else ""

    def _length(self) -> int:
        value = self.headers.get("Content-Length")
        if value is None:
            raise ValueError("请求必须提供 Content-Length")
        size = int(value)
        if size <= 0:
            raise ValueError("请求体不能为空")
        return size

    def _payload(self) -> dict:
        size = self._length()
        if size > MAX_BODY_BYTES:
            raise ValueError("JSON 请求体过大")
        data = json.loads(self.rfile.read(size))
        if not isinstance(data, dict):
            raise ValueError("请求必须是 JSON 对象")
        return data

    def _static(self, root: Path, route: str) -> None:
        asset = resolve_asset(root, route) or resolve_asset(root, "index.html")
        if asset is None:
            self._json(503, {"error": "前端未构建：请先在 webui 执行 npm run release"})
            return
        self._serve_file(asset)

    def _serve_file(self, path: Path, *, downloadable: bool = False, filename: str | None = None) -> None:
        size = path.stat().st_size
        byte_range = parse_range(self.headers.get("Range"), size)
        if self.headers.get("Range") and byte_range is None:
            self._send(416, b"", content_type(path), {"Content-Range": f"bytes */{size}"})
            return
        start, end = byte_range or (0, size - 1)
        self.send_response(206 if byte_range else 200)
        self.send_header("Content-Type", content_type(path))
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Accept-Ranges", "bytes")
        if downloadable:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename or path.name)}")
        if byte_range:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining:
                block = source.read(min(COPY_BYTES, remaining))
                if not block:
                    break
                self.wfile.write(block)
                remaining -= len(block)

    def _json(self, status: int, data: dict) -> None:
        self._send(
            status, json.dumps(data, ensure_ascii=False, allow_nan=False).encode(), "application/json; charset=utf-8"
        )

    def _send(self, status: int, body: bytes, mime: str, extra: dict | None = None) -> None:
        self.send_response(status)
        for name, value in {
            "Content-Type": mime,
            "Content-Length": str(len(body)),
            "Cache-Control": "no-store",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            **(extra or {}),
        }.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        LOGGER.debug("%s - %s", self.address_string(), format % args)
