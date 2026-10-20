# bili-music-segmenter

从直播视频中提取主播演唱片段，支持本地检测和 API 自动歌切。

需要 Python 3.12、[uv](https://docs.astral.sh/uv/)、FFmpeg；网易云识曲还需要 Node.js。

## API 自动歌切

```bash
uv sync --group api
uv run --group api -m segment.music_agent.cli --media input.mp4 --outdir output
```

先执行 `cp .env.example .env`，再填写项目根目录 `.env`：

```dotenv
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
OSS_ENDPOINT=
OSS_BUCKET=
OSS_PREFIX=music-agent
```

`DASHSCOPE_BASE_URL` 必须填写与 API key 对应的百炼接入地址，无默认值。OSS 使用私有 Bucket；临时音频在请求完成后删除。

输出为 MP4 视频片段和 JSON 处理记录，保存在 `--outdir` 指定目录。

常用参数：`--minimum-confidence`、`--minimum-singing-seconds`、`--boundary-context`、`--merge-gap`、`--no-title-model`、`--skip-shazam`、`--skip-netease`。完整参数见 `--help`。

网易云接口默认为 `http://127.0.0.1:3000/audio/match`，可用 `--netease-endpoint` 修改。本地服务启动：

```bash
npx NeteaseCloudMusicApi@latest
```

## 本地检测

```bash
uv sync --group local
uv run --group local inaseg.py --media input.mp4 --outdir output
```

使用 inaSpeechSegmenter 检测音乐并导出 MP3，不判断是否为主播本人演唱。可加 `--shazam`，或 `--netease --netease_endpoint http://127.0.0.1:3000/audio/match` 识曲重命名。

## 开发

```bash
uv sync --group api --group dev
uv run --group dev -m pytest
ruff check .
ruff format --check .
```

依赖统一由 `pyproject.toml` 与 `uv.lock` 管理：`local` 为本地模型，`api` 为云端 Agent，`recognizers` 为共享识曲依赖，`dev` 为测试工具。API 模式不安装 TensorFlow。

## Docker Compose

将视频放到 `input/input.mp4`；输出保存在 `output/`。API 模式先填写 `.env`。

```bash
docker compose -f compose.api.yaml build
docker compose -f compose.api.yaml run --rm api
docker compose -f compose.api.yaml down

# 本地检测
docker compose -f compose.local.yaml build
docker compose -f compose.local.yaml run --rm local
docker compose -f compose.local.yaml down
```

两种配置均自动启动 NeteaseCloudMusicApi，健康检查通过后开始处理，使用内部地址 `http://netease:3000/audio/match`。首次启动需要联网下载 npm 包，不向宿主机开放端口。

## Docker

```bash
docker build -t bili-music-segmenter .
docker build -f Dockerfile-gpu -t bili-music-segmenter:gpu .
docker run --rm -v "$PWD":/inaseg bili-music-segmenter uv run --frozen --group local inaseg.py --media input.mp4 --outdir output
```

GPU 镜像运行时增加 `--gpus all`，宿主机需安装 NVIDIA Container Toolkit。
