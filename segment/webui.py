"""Local-only WebUI for API music segmentation."""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from segment.webui_jobs import Jobs, build_command

HOST = "127.0.0.1"
DEFAULT_PORT = 7860
PAGE = Path(__file__).with_name("webui.html")
LOGGER = logging.getLogger(__name__)


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, jobs: Jobs, token: str, **kwargs) -> None:
        self.jobs = jobs
        self.token = token
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        if not self._local_host():
            return
        path = urlsplit(self.path).path
        if path == "/":
            import html

            page = PAGE.read_text(encoding="utf-8").replace("__TOKEN__", self.token)
            page = page.replace("__OUTDIR__", html.escape(os.getenv("WEBUI_OUTPUT_DIR", "output"), quote=True))
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        if not self._authorized():
            return
        if path == "/api/usage":
            self._json(200, self.jobs.usage.snapshot())
            return
        if not path.startswith("/api/jobs/"):
            self._json(404, {"error": "地址不存在"})
            return
        try:
            self._json(200, self.jobs.status(path.removeprefix("/api/jobs/")))
        except KeyError:
            self._json(404, {"error": "任务不存在，服务重启后任务状态不会保留"})
        except OSError as exc:
            LOGGER.exception("读取任务失败")
            self._json(500, {"error": str(exc)})

    def do_POST(self) -> None:
        if not self._local_host():
            return
        if not self._authorized():
            return
        if self.path != "/api/jobs":
            self._json(404, {"error": "地址不存在"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("请求体不能为空")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("请求必须是 JSON 对象")
            job_id = self.jobs.start(payload)
        except (ValueError, UnicodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        except OSError as exc:
            LOGGER.exception("启动任务失败")
            self._json(500, {"error": str(exc)})
            return
        self._json(201, {"id": job_id})

    def _local_host(self) -> bool:
        expected = f"{HOST}:{self.server.server_port}"
        if self.headers.get("Host") != expected:
            self._json(403, {"error": "请使用启动时显示的本机地址访问"})
            return False
        return True

    def _authorized(self) -> bool:
        # A per-launch token prevents other websites from invoking local file operations.
        if not secrets.compare_digest(self.headers.get("X-WebUI-Token", ""), self.token):
            self._json(403, {"error": "访问令牌无效，请刷新页面"})
            return False
        return True

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", choices=(HOST, "0.0.0.0"), default=HOST)
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    logging.basicConfig(level=logging.INFO)
    jobs = Jobs(build_command)
    handler = partial(Handler, jobs=jobs, token=secrets.token_hex())
    with ThreadingHTTPServer((args.host, args.port), handler) as server:
        print(f"WebUI: http://{HOST}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            jobs.close()


if __name__ == "__main__":
    main()
