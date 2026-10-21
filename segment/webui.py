"""Local-only WebUI for API music segmentation.

The page itself is a static Next.js export served from ``segment/webui_dist``; this module only
implements the JSON API and read-only media serving. Build the frontend with ``webui`` scripts
(see the project README) before starting the service.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from segment.logs import configure_logging, server_log_path
from segment.webui_jobs import (
    DEFAULT_MAX_JOBS,
    JobLimitReached,
    Jobs,
    build_batch,
    input_dir,
    list_inputs,
)
from segment.webui_static import content_type, parse_range, resolve_asset

HOST = "127.0.0.1"
DEFAULT_PORT = 7860
MAX_BODY_BYTES = 64 * 1024
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = Path(__file__).with_name("webui_dist")
LOGGER = logging.getLogger(__name__)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    timeout = 30

    def handle_error(self, request, client_address) -> None:
        # Never stop the whole service just because one client aborted while reading the response.
        LOGGER.exception("处理请求失败：%s", client_address)


class Handler(BaseHTTPRequestHandler):
    server_version = "BiliMusicSegmenter"
    sys_version = ""

    def __init__(self, *args, jobs: Jobs, token: str, **kwargs) -> None:
        self.jobs = jobs
        self.token = token
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        if not self._local_host():
            return
        route = urlsplit(self.path).path
        if route.startswith("/api/"):
            self._api_get(route)
            return
        # <script> and <link> cannot send headers, so the bundle is served without a token. It contains
        # no data; every API call still requires the per-launch token below.
        self._static(route)

    def do_POST(self) -> None:
        if not self._local_host():
            return
        if not self._authorized():
            self._discard_body()
            return
        route = urlsplit(self.path).path
        if route.startswith("/api/jobs/") and route.endswith("/stop"):
            self._stop_job(route.removeprefix("/api/jobs/").removesuffix("/stop"))
            return
        if route != "/api/jobs":
            self._json(404, {"error": "地址不存在"})
            return
        try:
            job_id = self.jobs.start(self._read_payload())
        except (ValueError, UnicodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        except JobLimitReached as exc:
            self._json(429, {"error": str(exc)})
            return
        except OSError as exc:
            LOGGER.exception("启动任务失败")
            self._json(500, {"error": str(exc)})
            return
        self._json(201, {"id": job_id})

    def _api_get(self, route: str) -> None:
        if not self._authorized():
            return
        if route == "/api/bootstrap":
            # Single request so the page can render before its first poll completes.
            self._json(
                200,
                {
                    "version": 2,
                    "input_dir": str(input_dir()),
                    "output_dir": os.getenv("WEBUI_OUTPUT_DIR", "output"),
                    "max_jobs": self.jobs.max_jobs,
                },
            )
            return
        if route == "/api/inputs":
            self._json(200, {"directory": str(input_dir()), "files": list_inputs()})
            return
        if route == "/api/usage":
            self._json(200, self.jobs.usage.snapshot())
            return
        if route == "/api/history":
            self._json(200, {"entries": self.jobs.history.load()})
            return
        if route.startswith("/api/jobs/"):
            job_id, _, action = route.removeprefix("/api/jobs/").partition("/")
            self._job_get(job_id, action)
            return
        self._json(404, {"error": "地址不存在"})

    def _job_get(self, job_id: str, action: str) -> None:
        if not job_id:
            self._json(404, {"error": "地址不存在"})
            return
        if action in {"", "clips"}:
            self._job_status(job_id)
            return
        if action == "log":
            self._job_log(job_id)
            return
        if action.startswith("clip/"):
            self._clip(job_id, action.removeprefix("clip/"))
            return
        self._json(404, {"error": "地址不存在"})

    def _job_status(self, job_id: str) -> None:
        try:
            self._json(200, self.jobs.status(job_id))
        except KeyError:
            self._json(404, {"error": "任务不存在，服务重启后任务状态不会保留"})
        except OSError as exc:
            LOGGER.exception("读取任务失败")
            self._json(500, {"error": str(exc)})

    def _job_log(self, job_id: str) -> None:
        """Return only the log bytes after ``offset`` so the page never re-renders the whole log."""
        try:
            start = int(self.headers.get("X-Log-Offset", "0"))
        except ValueError:
            start = 0
        try:
            item = int(self.headers.get("X-Log-Item", "0"))
            chunk = self.jobs.log_chunk(job_id, item, max(0, start))
        except KeyError:
            self._json(404, {"error": "任务不存在"})
            return
        except IndexError:
            self._json(400, {"error": "日志序号无效"})
            return
        self._json(200, chunk)

    def _clip(self, job_id: str, encoded_name: str) -> None:
        name = unquote(encoded_name)
        try:
            path = self.jobs.clip_path(job_id, name)
        except KeyError:
            self._json(404, {"error": "任务不存在"})
            return
        if path is None:
            self._json(404, {"error": "片段不存在"})
            return
        # A plain <a download> link can only carry the flag in the URL, not in a header.
        query_download = parse_qs(urlsplit(self.path).query).get("download") == ["1"]
        requested = self.headers.get("X-Download") == "1" or query_download
        self._serve_file(path, downloadable=requested)

    def _static(self, route: str) -> None:
        asset = resolve_asset(DIST_DIR, route) or resolve_asset(DIST_DIR, "index.html")
        if asset is None:
            self._json(503, {"error": "前端未构建：请先构建 webui 并复制到 segment/webui_dist/"})
            return
        self._serve_file(asset)

    def _serve_file(self, path: Path, *, downloadable: bool = False) -> None:
        size = path.stat().st_size
        byte_range = parse_range(self.headers.get("Range"), size)
        if self.headers.get("Range") and byte_range is None:
            self._send(416, b"", content_type(path), {"Content-Range": f"bytes */{size}"})
            return
        start, end = byte_range or (0, size - 1)
        length = end - start + 1
        self.send_response(206 if byte_range else 200)
        self.send_header("Content-Type", content_type(path))
        self.send_header("Content-Length", str(length))
        # Media is immutable per job; the bundle is content-addressed by Next.
        self.send_header("Cache-Control", "private, max-age=3600" if path.suffix != ".html" else "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        if downloadable:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(path.name)}")
        if byte_range:
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                block = handle.read(min(256 * 1024, remaining))
                if not block:
                    break
                self.wfile.write(block)
                remaining -= len(block)

    def _body(self) -> bytes:
        length = self.headers.get("Content-Length")
        if length is None:
            # Without a declared length the only end of body is EOF, so never block waiting for more.
            try:
                return self.rfile.read(MAX_BODY_BYTES + 1)
            except TimeoutError:
                raise ValueError("请求必须提供 Content-Length 或关闭写入端") from None
        try:
            size = int(length)
        except ValueError:
            raise ValueError("Content-Length 无效") from None
        if size <= 0:
            raise ValueError("请求体不能为空")
        if size > MAX_BODY_BYTES:
            raise ValueError("请求体过大")
        return self.rfile.read(size)

    def _stop_job(self, job_id: str) -> None:
        try:
            self.jobs.stop_current(job_id)
        except KeyError:
            self._json(404, {"error": "任务不存在"})
            return
        self._json(200, {"stopped": True})

    def _read_payload(self) -> dict:
        payload = json.loads(self._body())
        if not isinstance(payload, dict):
            raise ValueError("请求必须是 JSON 对象")
        return payload

    def _discard_body(self) -> None:
        # Consume the request body before replying, otherwise closing early resets the connection.
        try:
            self._body()
        except ValueError:
            pass

    def _local_host(self) -> bool:
        port = self.server.server_port
        if self.headers.get("Host") not in {f"{HOST}:{port}", f"localhost:{port}"}:
            self._json(403, {"error": "请使用启动时显示的本机地址访问"})
            return False
        return True

    def _authorized(self) -> bool:
        # A per-launch token prevents other websites from invoking local file operations.
        supplied = self.headers.get("X-WebUI-Token") or self._query_token()
        if not secrets.compare_digest(supplied, self.token):
            self._json(403, {"error": "访问令牌无效，请刷新页面"})
            return False
        return True

    def _query_token(self) -> str:
        """<video> and download links cannot send headers, so they pass the same token in the URL."""
        values = parse_qs(urlsplit(self.path).query).get("token", [])
        return values[0] if len(values) == 1 else ""

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type_value: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type_value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        LOGGER.debug("%s - %s", self.address_string(), format % args)


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("必须为正整数")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", choices=(HOST, "0.0.0.0"), default=HOST)
    parser.add_argument("--max-jobs", type=positive_int, default=DEFAULT_MAX_JOBS, help="同时运行的子进程任务上限")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    configure_logging(getattr(logging, args.log_level), log_file=server_log_path())
    jobs = Jobs(build_batch, max_jobs=args.max_jobs)
    token = secrets.token_hex()
    handler = partial(Handler, jobs=jobs, token=token)
    with Server((args.host, args.port), handler) as server:
        shown = HOST if args.host == "0.0.0.0" else args.host
        # The token is part of the URL: the built bundle is static and cannot be templated per launch.
        print(f"WebUI: http://{shown}:{server.server_port}/?token={token}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            jobs.close()


if __name__ == "__main__":
    main()
