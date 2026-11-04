"""Serve the persistent Material 3 browser workspace and its local API."""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import signal
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from segment.logs import configure_logging, log_dir, server_log_path
from segment.music_agent.audio_cache import clean_audio_cache
from segment.music_agent.config import load_config
from segment.music_agent.media_cache import clean_local_cache
from segment.music_agent.storage import create_storage
from segment.usage import UsageTotals
from segment.webui_jobs import Jobs
from segment.workspace_execution import Execution
from segment.workspace_http import HOST, WorkspaceHTTP
from segment.workspace_process import ProcessRunner
from segment.workspace_store import DocumentStore
from segment.workspace_uploads import Uploads

DEFAULT_PORT = 7860
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = Path(__file__).with_name("webui_dist")
LOGGER = logging.getLogger(__name__)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    timeout = 30

    def handle_error(self, request, client_address) -> None:
        LOGGER.exception("处理请求失败：%s", client_address)


class Handler(WorkspaceHTTP):
    def __init__(self, *args, jobs: Jobs, token: str, **kwargs):
        self.jobs, self.token = jobs, token
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        if not self._authorized():
            return
        route = urlsplit(self.path).path
        try:
            if not route.startswith("/api/") and method == "GET":
                self._static(DIST_DIR, route)
            elif route.startswith("/api/uploads"):
                self._uploads(method, route)
            elif route.startswith("/api/jobs/"):
                self._job(method, route)
            else:
                self._root(method, route)
        except (ValueError, UnicodeError, IndexError) as error:
            self._json(400, {"error": str(error)})
        except (KeyError, FileNotFoundError) as error:
            self._json(404, {"error": f"记录或文件不存在：{error}"})
        except (BrokenPipeError, ConnectionResetError):
            LOGGER.info("浏览器已断开连接")
        except Exception as error:
            LOGGER.exception("请求执行失败")
            self._json(500, {"error": str(error)})

    def _root(self, method: str, route: str) -> None:
        if method == "POST" and route == "/api/downloads":
            self._json(201, {"id": self.jobs.start_download(self._payload())})
        elif method == "POST" and route == "/api/jobs":
            self._json(201, {"id": self.jobs.start(self._payload())})
        elif method == "GET" and route == "/api/bootstrap":
            self._json(
                200,
                {
                    "version": 3,
                    "defaults": self.jobs.defaults,
                    "active_job_ids": [
                        job["id"] for job in self.jobs.store.list("jobs") if job["state"] in {"queued", "running"}
                    ],
                },
            )
        elif method == "GET" and route == "/api/history":
            self._json(200, {"entries": self.jobs.history()})
        elif method == "GET" and route == "/api/usage":
            self._json(200, self.jobs.usage.snapshot())
        else:
            self._json(404, {"error": "地址不存在"})

    def _uploads(self, method: str, route: str) -> None:
        identity = route.removeprefix("/api/uploads").removeprefix("/")
        if method == "GET" and not identity:
            referenced = {value for job in self.jobs.store.list("jobs") for value in job["upload_ids"]}
            files = [{**value, "referenced": value["id"] in referenced} for value in self.jobs.store.list("uploads")]
            self._json(200, {"files": files})
        elif method == "POST" and not identity:
            self._json(201, self.jobs.uploads.register(self._payload()))
        elif method == "PUT" and identity:
            self._json(200, self.jobs.uploads.receive(identity, self.rfile, self._length()))
        elif method == "DELETE" and identity:
            self.jobs.uploads.remove(identity)
            self._json(200, {"deleted": True})
        else:
            self._json(404, {"error": "地址不存在"})

    def _job(self, method: str, route: str) -> None:
        identity, _, action = route.removeprefix("/api/jobs/").partition("/")
        if method == "GET":
            self._job_get(identity, action)
        elif method == "POST" and action == "retry":
            self._json(200, {"id": self.jobs.retry(identity)})
        elif method == "POST" and action == "stop":
            self.jobs.stop_current(identity)
            self._json(200, {"stopped": True})
        elif method == "DELETE" and not action:
            self.jobs.delete(identity)
            self._json(200, {"deleted": True})
        else:
            self._json(404, {"error": "地址不存在"})

    def _job_get(self, identity: str, action: str) -> None:
        if not action:
            self._json(200, self.jobs.status(identity))
        elif action == "log":
            index, offset = int(self.headers.get("X-Log-Item", "0")), int(self.headers.get("X-Log-Offset", "0"))
            if index < 0 or offset < 0:
                raise ValueError("日志位置无效")
            self._json(200, self.jobs.log_chunk(identity, index, offset))
        elif action == "archive":
            self._serve_file(self.jobs.archive(identity), downloadable=True)
        elif action.startswith("clip/"):
            self._serve_file(
                self.jobs.clip_path(identity, action.removeprefix("clip/")), downloadable=self._query("download") == "1"
            )
        else:
            self._json(404, {"error": "地址不存在"})


def create_jobs(root: Path, *, runner=None, cleanup=None) -> Jobs:
    root = root.resolve()
    store = DocumentStore(root / "workspace.sqlite3")
    uploads = Uploads(root / "uploads", store)
    usage = UsageTotals()
    execution = Execution(store, runner or ProcessRunner(), root, usage=usage)

    def clean(owner):
        if any(owner in item["owners"] for item in store.list("audio_cache")):
            clean_audio_cache(store, owner, create_storage(load_config()))
        clean_local_cache(store, owner)

    return Jobs(
        store,
        uploads,
        {
            "root": root,
            "execution": execution,
            "cleanup": cleanup or clean,
            "legacy_path": log_dir() / "webui-history.json",
            "usage": usage,
        },
    )


def _terminate(signum, frame) -> None:
    raise SystemExit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", choices=(HOST, "0.0.0.0"), default=HOST)
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("WEBUI_DATA_DIR", "data/webui")))
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _terminate)
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    configure_logging(getattr(logging, args.log_level), log_file=server_log_path())
    jobs, token = create_jobs(args.data_dir), secrets.token_hex()
    handler = partial(Handler, jobs=jobs, token=token)
    with Server((args.host, args.port), handler) as server:
        print(f"WebUI: http://{HOST}:{server.server_port}/?token={token}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            jobs.close()


if __name__ == "__main__":
    main()
