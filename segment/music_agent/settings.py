"""Environment overrides for CLI defaults, shared by WebUI subprocesses."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PREFIX = "MUSIC_AGENT_"


def apply_environment(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    for action in parser._actions:
        if action.required or action.dest == "help":
            continue
        value = os.getenv(ENV_PREFIX + action.dest.upper())
        if value is None:
            continue
        if isinstance(action, argparse._StoreTrueAction):
            if value.lower() not in {"true", "false"}:
                parser.error(f"{ENV_PREFIX}{action.dest.upper()} 必须是 true 或 false")
            action.default = value.lower() == "true"
        else:
            action.default = value
    return parser
