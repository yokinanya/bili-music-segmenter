# bili-music-segmenter

分析直播录像，定位完整单曲并切出演唱片段。支持浏览器上传和 yt-dlp 链接下载，界面是 Material 3 工具操作中心，任务由 Python 服务持久执行。

需要 Python 3.12、uv、FFmpeg、Node.js 20+。

## 启动

```bash
cp .env.example .env      # 填写 GEMINI_API_KEY
uv sync
uv run -m segment.webui
```

用控制台打印的带令牌地址打开页面。默认监听 `127.0.0.1:7860`，`--port` 可改端口；令牌每次启动更换，普通 API 需要请求头认证。

配置项：

| 变量 | 说明 |
| --- | --- |
| `GEMINI_API_KEY` | 必填，Google Gemini 官方接口密钥 |
| `GEMINI_PROXY` | 需要代理时填写，必须带协议 |
| `GEMINI_AUDIO_MODEL` | 覆盖音频模型，默认 `gemini-4-hydrogen` |
| `GEMINI_BASE_URL` | 自定义接入地址，一般留空 |
| `WEBUI_DATA_DIR` | 任务数据目录，默认 `data/webui` |
| `MUSIC_AGENT_NETEASE_COOKIE` | 网易云 Cookie，与下载 Cookie 独立 |

## 工作流程

1. 扫描：Gemini 听整段音频，一次给出每首歌的起止点、分类、歌名线索和主播报幕原话。默认按 1200 秒分块，总长不超过一块时整场单次调用。
2. 识曲：Shazam 与网易云分别识别各片段。
3. 判定：两边歌名一致（繁简、版本后缀归一化后）直接填入标题；不一致时标题留空，界面列出候选供点选或手填。歌手只作展示。
4. 切分：只改标题时复用已导出视频并改名，不重新编码，也不覆盖手动修改。

不再有模型二次处理：识曲结果直接决定标题与切分。歌名有疑问时由人工选择，扫描理由和报幕原话保留在 JSON 里供核对。

背景录音里的歌不算，只有主播本人清晰持续的演唱才切。切分保留有证据的前奏、尾奏、间奏和换气，跨块去重后结尾延长 2 秒，遇到下一首起点或视频结尾只延长到边界。

## 网易云识曲

同一片段从 6、12、20、30 秒处各识别一次，按归一化歌名多数决；cover、伴奏、纯享版等版本附注算同一票，平票才标记冲突。起点位置会影响结果，不能只取首个命中。

采样串行执行，`--recognizer-timeout` 同时是整体时限：单点超时按剩余时间裁剪（向上取整为整数秒），用尽后跳过剩余采样点并沿用已有结果。单点网络抖动或子进程失败只丢弃该采样点，不会让整首歌无法识别；只有全部采样点都失败时才报错，并带上子进程的真实原因。

指纹工具 `vendor/ncm-afp/audio_match.js` 从 NeteaseCloudMusicApi 4.32.0 提取，Node 直接请求上游，不需要单独启动服务。

## 结果与任务

- 支持页面试听、片段下载、整批 ZIP，可编辑标题、歌手、起止秒数后重新导出。
- 任务与文件留在 `data/webui/`，保留至手动删除。服务重启后未完成任务标记为中断，点击续跑复用成功检查点。
- 用量按实际模型请求记账，费用按 Gemini 官方价估算；未知价格或缺失 usage 会标记统计不完整。

## 参数

界面只暴露影响结果的选项：最低置信度、最短演唱、最短候选、识曲超时、Shazam 与网易云开关。其余固定在代码中：

| 项 | 固定值 |
| --- | --- |
| 扫描块时长 / 上下文 | 1200 秒 / 30 秒 |
| 候选处理并发 | 3 |
| 模型请求并发 | 3 |
| 识曲请求并发 | 2 |
| 网易云识曲并发 | 1 |
| 媒体进程并发 | CPU 数与 2 的较小值 |

## 界面与构建

固定 `@material/web@2.5.0`，蓝紫主题由 `#3f5ad4` 生成，本地字体与 SVG 图标，无外部请求。1280px 三栏，840px 双栏，更窄单栏加面板标签；`Alt+1/2/3` 切换区域。

```bash
cd webui
npm ci
npm run release        # 构建并复制到 segment/webui_dist
```

Python 直接托管静态产物，运行时不需 Next.js 服务。改了 `webui/src` 必须重新 `release`，否则界面仍是旧构建。

## 命令行与 Docker

```bash
uv run -m segment.music_agent.cli --media video.mp4 --outdir output
docker compose -f compose.api.yaml up --build -d
```

CLI 与 WebUI 共用同一套分析与切片流程。

## 开发验证

```bash
uv sync --group dev
ruff check . && ruff format --check .
uv run --group dev -m pytest -q
npm --prefix webui run typecheck
npm test --prefix webui
```

真实模型与网站账户链路需要有效配置，单元测试不覆盖。
