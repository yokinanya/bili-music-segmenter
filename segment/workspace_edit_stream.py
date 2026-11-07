"""Stream measured edit progress while the normal result edit runs."""

from __future__ import annotations

import json
import logging
import subprocess
import time

LOGGER = logging.getLogger(__name__)
STREAM_CONTENT_TYPE = "application/x-ndjson"


def stream_edit(handler, identity: str, clip_id: str) -> None:
    payload = handler._payload()
    handler.send_response(200)
    handler.send_header("Content-Type", STREAM_CONTENT_TYPE)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.close_connection = True
    started = time.monotonic()
    connected = True

    def report(event: dict) -> None:
        nonlocal connected
        if not connected:
            return
        data = {**event, "elapsed_seconds": time.monotonic() - started}
        try:
            handler.wfile.write((json.dumps(data, ensure_ascii=False, allow_nan=False) + "\n").encode())
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            connected = False
            LOGGER.info("编辑进度连接已断开，服务端继续完成本次保存")

    try:
        clip = handler.jobs.edit_clip(identity, clip_id, payload, progress=report)
        report({"stage": "succeeded", "clip": clip})
    except Exception as error:
        message = str(error)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            message += "\n" + str(error.stderr)
        LOGGER.exception("编辑片段失败：%s\n%s", clip_id, message)
        report({"stage": "failed", "error": message})
