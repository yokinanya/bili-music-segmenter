# bili-music-segmenter

一个只保留歌切功能的命令行工具：输入本地媒体文件，使用 `inaSpeechSegmenter` 检测音乐片段，导出 MP3，并可选用 Shazam 或外部网易云服务识别后重命名。

## 功能

- 本地音频/视频文件切歌。
- 导出 MP3 音频片段。
- 可选 Shazam 或网易云识别、重命名和封面保存。
- CPU 与 GPU Docker 镜像。

## Docker

构建 CPU 镜像：

```bash
docker build -t bili-music-segmenter .
```

构建 GPU 镜像：

```bash
docker build -f Dockerfile-gpu -t bili-music-segmenter:gpu .
```

切本地文件：

```bash
docker run --rm -v "$(pwd)":/inaseg bili-music-segmenter \
  python /inaseg/inaseg.py \
  --media /inaseg/input.mp4 \
  --outdir /inaseg/output
```

GPU 运行时需要宿主机已安装 NVIDIA Container Toolkit：

```bash
docker run --rm --gpus all -v "$(pwd)":/inaseg bili-music-segmenter:gpu \
  python /inaseg/inaseg.py \
  --media /inaseg/input.mp4 \
  --outdir /inaseg/output
```

## 本地运行

系统需要先安装 `ffmpeg`、`ffprobe`。启用网易云识别时还需要 `node`。

```bash
uv sync
uv run inaseg.py --media input.mp4 --outdir output
```

## Shazam 识别

加上 `--shazam` 后，会对导出的片段调用真实 Shazam 识别，并按识别结果重命名：

```bash
python inaseg.py --media input.mp4 --outdir output --shazam
```

保存封面：

```bash
python inaseg.py --media input.mp4 --outdir output --shazam --shazam_coverart output/covers
```

## 网易云识别

网易云 `/audio/match` 需要 `audioFP` 音频指纹，不直接接收本地音频文件。本工具会先用 `ffmpeg` 从片段中抽取 3 秒 8kHz PCM，再通过 `vendor/ncm-afp` 生成 `audioFP`，最后把 `duration` 和 `audioFP` 作为 query 参数直接请求 NeteaseCloudMusicApi 路由。

`--netease_endpoint` 填标准 NeteaseCloudMusicApi 的 `/audio/match` 地址即可。接口不强制登录；如你的部署需要登录态，可以用 `--netease_cookie` 透传 cookie。

本地启动 NeteaseCloudMusicApi：

```bash
npx NeteaseCloudMusicApi@latest
```

默认服务地址为 `http://127.0.0.1:3000`，对应识别接口 `http://127.0.0.1:3000/audio/match`。

NeteaseCloudMusicApi 自带 demo 的逻辑是：在当前播放位置点击 Clip 后录 3 秒，生成 `audioFP`，再 `POST /audio/match?duration=3&audioFP=...`。本工具默认 `--netease_offsets 6,12,20,30`，跳过切片开头的完整优先缓冲后尝试多个 3 秒窗口；全部无匹配时会抛出每个窗口的 `noMatchReason`。

```bash
python inaseg.py \
  --media input.mp4 \
  --outdir output \
  --netease \
  --netease_endpoint http://127.0.0.1:3000/audio/match
```

## 识别回退

启用 `--recognizer_fallback` 后，主识别平台失败会显式记录 warning，然后调用另一个平台。

Shazam 优先，失败后回退到网易云：

```bash
python inaseg.py \
  --media input.mp4 \
  --outdir output \
  --shazam \
  --recognizer_fallback \
  --netease_endpoint http://127.0.0.1:3000/audio/match
```

网易云优先，失败后回退到 Shazam：

```bash
python inaseg.py \
  --media input.mp4 \
  --outdir output \
  --netease \
  --recognizer_fallback \
  --netease_endpoint http://127.0.0.1:3000/audio/match
```

## 参数

默认配置偏向“完整优先”，会在检测出的音乐段前后保留缓冲，减少歌曲首尾被截断。

- `--media`：本地媒体路径，必填。
- `--outdir`：导出目录，默认使用系统临时目录。
- `--shazam`：导出后调用 Shazam 识别。
- `--shazam_coverart`：保存 Shazam 封面的目录。
- `--netease`：导出后调用外部网易云识别服务。
- `--netease_endpoint`：NeteaseCloudMusicApi `/audio/match` 地址，启用 `--netease` 时必填。
- `--netease_coverart`：保存网易云封面的目录。
- `--netease_cookie`：传给 NeteaseCloudMusicApi 的网易云 cookie。
- `--netease_timeout`：网易云识别服务请求超时，单位秒。
- `--netease_offsets`：生成网易云 `audioFP` 前尝试跳过的秒数列表，默认 `6,12,20,30`。
- `--netease_rejects`：丢弃指定网易云识别结果，格式为 `歌名|艺人`，多项用逗号分隔，默认丢弃 `劫|黄霄雲`。
- `--recognizer_fallback`：主识别失败时回退到另一个识别平台。
- `--soundonly`：导出音频 MP3 片段，默认开启。
- `--keep_video`：保留视频/音频片段，不转换为 MP3。
- `--seg_connect`：相邻音乐段合并阈值，单位秒。
- `--cleanup`：完成后删除原始下载文件。
- `--max_segment_length`：长媒体分块处理阈值，单位秒。

## 输出

导出的文件位于 `--outdir`，命名格式为：

```text
原文件名_序号.mp3
```

启用识别后，识别成功的文件会被重命名为：

```text
原文件名_序号_歌曲名 by 艺人.mp3
```
