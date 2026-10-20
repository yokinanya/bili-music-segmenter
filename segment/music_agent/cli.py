"""Command-line entry point for the conservative music-cut agent."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from segment.music_agent.agent import run_agent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media", type=Path, required=True, help="输入视频或包含音轨的媒体文件")
    parser.add_argument("--outdir", type=Path, required=True, help="切片与 manifest 输出目录")
    parser.add_argument("--netease-endpoint", default="http://127.0.0.1:3000/audio/match")
    parser.add_argument("--netease-cookie", default="")
    parser.add_argument("--chunk-seconds", type=int, default=600)
    parser.add_argument("--chunk-context", type=int, default=30)
    parser.add_argument("--boundary-context", type=int, default=20)
    parser.add_argument("--minimum-candidate-seconds", type=float, default=30)
    parser.add_argument("--minimum-singing-seconds", type=float, default=30)
    parser.add_argument("--minimum-confidence", type=float, default=0.85)
    parser.add_argument("--merge-gap", type=float, default=10)
    parser.add_argument("--title-model", default="qwen3.8-flash")
    parser.add_argument("--no-title-model", action="store_true", help="不使用第二个文本模型处理识曲冲突")
    parser.add_argument("--recognizer-timeout", type=int, default=60)
    parser.add_argument("--skip-shazam", action="store_true")
    parser.add_argument("--skip-netease", action="store_true")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.chunk_seconds <= 0:
        parser.error("--chunk-seconds 必须大于 0")
    if args.chunk_context < 0 or args.boundary_context < 0:
        parser.error("上下文时长不能为负")
    if not 0 < args.minimum_confidence <= 1:
        parser.error("--minimum-confidence 必须大于 0 且不超过 1")
    if args.minimum_candidate_seconds <= 0 or args.minimum_singing_seconds <= 0:
        parser.error("最短候选和最短演唱时长必须大于 0")
    if args.merge_gap < 0 or args.recognizer_timeout <= 0:
        parser.error("合并间隔不能为负，识曲超时必须为正")
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    manifest = asyncio.run(
        run_agent(
            args.media,
            args.outdir,
            chunk_seconds=args.chunk_seconds,
            chunk_context_seconds=args.chunk_context,
            boundary_context_seconds=args.boundary_context,
            minimum_candidate_seconds=args.minimum_candidate_seconds,
            minimum_singing_seconds=args.minimum_singing_seconds,
            minimum_confidence=args.minimum_confidence,
            merge_gap_seconds=args.merge_gap,
            use_title_model=not args.no_title_model,
            title_model=args.title_model,
            use_shazam=not args.skip_shazam,
            use_netease=not args.skip_netease,
            netease_endpoint=args.netease_endpoint,
            netease_cookie=args.netease_cookie,
            recognizer_timeout=args.recognizer_timeout,
        )
    )
    print(manifest)


if __name__ == "__main__":
    main()
