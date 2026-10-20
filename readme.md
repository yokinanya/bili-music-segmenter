# bili-music-segmenter

从直播视频中提取主播演唱歌曲，支持本地检测和 API 自动歌切。
API 扫描和边界复核以完整单曲为目标，保留有证据属于本次演唱的前奏、内部间奏、尾奏、换气与短暂插话，
不以第一句/最后一句人声作为固定首尾，仅在明确换歌、结束表演或独立聊天时拆段。
最终导出前，默认由 `qwen3.8-flash` 审查全场候选、初步边界与识曲结果；可通过
`--summary-model` / `MUSIC_AGENT_SUMMARY_MODEL` 指定总结模型，独立于标题裁决开关。
总结模型仅指出疑点、请求更大上下文的音频复核，不凭文本直接修改切点或歌名；复核结果重新识曲后才导出。
全场总结执行一次，不自动循环；不自动合并跨候选结果。
音频边界复核返回同一次歌曲表演的区间分组，在最短时长过滤之前合并同组的间奏和短尾段；
不同歌曲分组不会仅因间隔较短而合并（旧 `--merge-gap` 参数保留接收，但不再驱动跨组自动合并）。
当输出首尾触及输入边界或模型明确标记截断时，自动倍增上下文重新听取，直到找到边界或到达媒体自然首尾；
每次音频请求及输入范围保留在 `boundary_attempts`，不设置任意重试次数，也不会假装找回媒体之外的内容。
多区间响应缺少有效分组会明确报错，而不是悄悄拆成碎片；该流程仍依赖音频模型判断，不能保证声学准确率。
总结和新增复核均计入用量与费用，记录写入候选的 `final_summary`、`final_audio_review`，异常明确终止。
边界只能在实际送入模型的音频范围内确定；`--chunk-context` / `MUSIC_AGENT_CHUNK_CONTEXT`（默认 30 秒）控制扫描上下文，
`--boundary-context` / `MUSIC_AGENT_BOUNDARY_CONTEXT`（默认 20 秒）控制候选首尾的复核上下文。
如果原候选漏掉的前奏超出上下文范围，仍无法保证找回，不会用固定向前补秒数冒充准确边界。

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
S3_ACCESS_KEY_ID=
S3_ACCESS_KEY_SECRET=
S3_ENDPOINT=
S3_BUCKET=
S3_REGION=
S3_PREFIX=music-agent
S3_ADDRESSING_STYLE=path
```

`DASHSCOPE_BASE_URL` 必须填写与 API key 对应的百炼接入地址，无默认值。
存储使用 boto3 的通用 S3 接口，可连接 AWS S3、MinIO、Cloudflare R2 等 S3 兼容服务；不再读取 `OSS_*` 配置。
`S3_ENDPOINT` 可填写域名或域名加端口（如 `s3.example.com:9000`），省略协议时自动使用 `https://`；也可显式填写 `http://` 或 `https://`。
`S3_REGION` 填写服务要求的区域（例如 AWS 的 `us-east-1`、R2 的 `auto`）。
`S3_ADDRESSING_STYLE` 支持 `path`（默认）、`virtual` 和 `auto`；AWS S3 通常使用 `virtual`。
需要特定 User-Agent 的服务可配置 `S3_USER_AGENT`，设置为服务要求的值；未设置或留空时使用 SDK 默认值。
该配置只影响本程序发往 S3 的请求，不控制云端模型访问预签名 URL 时的 User-Agent。
Bucket 保持私有，凭据需具有指定前缀下的 PutObject、GetObject、DeleteObject 权限。
音频以一小时有效的 S3 V4 预签名 GET URL 提交给云端模型，请求完成或模型调用失败后删除临时对象；清理失败会显式报错。
Endpoint 必须可被云端模型访问，仅本机可达的 MinIO 地址不能用于云端识别。
`S3_PREFIX` 默认 `music-agent`，可留空使用桶根目录；已有 `.env` 需要手动填写新的 `S3_*` 配置，旧 OSS 凭据不会自动迁移。

输出为 MP4 视频片段和 JSON 处理记录，保存在 `--outdir` 指定目录。
扫描歌名提示优先采用证据支持的中文正式名称。识曲发生冲突，或匹配结果含英文/罗马字歌名、艺人名时，
自动将当前片段交给音频模型听取歌词、识别演唱语言和版本，并核对正式中文名称；该步骤独立于文本标题裁决开关。
原曲与中文填词版共用伴奏时，以实际歌词证据选择识曲候选，不仅因为某项名称含中文就选它。
中文显示名须附名称依据，繁体中文转简体；没有可靠中文正式名称的英文作品保留原名，不强行直译。
音频版本判断缺少清晰歌词或证据不足时保留 unresolved，不伪造成功；原始参考和音频判断均写入处理记录。
此步骤会增加临时音频上传及模型费用，无法保证模型给出的官方别名或歌词完全准确。
Shazam 明确返回空匹配数组时记录 no_match；缺少 track 但并非明确无匹配的异常响应会记录明确错误，而非 KeyError。

分块扫描默认并发执行 3 个「音频提取 → 上传 → 模型扫描 → 删除」任务；使用
`MUSIC_AGENT_SCAN_CONCURRENCY=1` 或 `--scan-concurrency 1` 可改为串行。
边界复核和导出仍为串行，扫描结果按分块顺序汇总后合并候选。
并发会增加 CPU、磁盘、带宽及 API 限流压力；失败会明确报错，不跳过失败分块。

音频和文本模型返回无效 JSON 时，仅重试当前调用，默认额外重试 3 次（最多调用 4 次），不重跑成功分块。
可用 `MUSIC_AGENT_JSON_RETRIES=0` 禁用，或设为其他非负整数调整。
每次响应均计入 token 和费用；日志记录模型、尝试次数、结束原因、解析错误及原始文本（可能包含音频内容的转写，请妥善保管日志）。
重试耗尽后任务明确失败，不修造结果、不跳过分块。该策略只处理 JSON 语法、空响应和顶层格式错误，
不为 HTTP/网络错误增加另一层重试，也不重试后续业务字段校验错误；原有 SDK 网络重试保持不变。

常用参数：`--minimum-confidence`、`--minimum-singing-seconds`、`--boundary-context`、`--merge-gap`、`--no-title-model`、`--skip-shazam`、`--skip-netease`。完整参数见 `--help`。

网易云接口默认为 `http://127.0.0.1:3000/audio/match`，可用 `--netease-endpoint` 修改。本地服务启动：

```bash
npx NeteaseCloudMusicApi@latest
```

## WebUI（API 自动歌切）

完成上面的 `.env` 配置后启动：

```bash
uv run --group api -m segment.webui
```

浏览器打开 `http://127.0.0.1:7860`，填写本机视频路径与输出目录，点击「开始歌切」。
界面显示任务状态与实时日志，不再提供高级设置。处理参数通过服务端 `.env` 中的 `MUSIC_AGENT_*` 环境变量配置，
对应 CLI 参数，例如 `MUSIC_AGENT_MINIMUM_CONFIDENCE` 对应 `--minimum-confidence`，`MUSIC_AGENT_SKIP_NETEASE=true` 对应 `--skip-netease`。
相对路径以项目根目录为基准；视频不通过浏览器上传，检测仍会按 API 流程使用云端服务并产生费用。
网易云识曲需要单独启动上述接口服务，或设置 `MUSIC_AGENT_SKIP_NETEASE=true`。

使用 `--port 端口号` 更换端口。WebUI 默认仅绑定本机 `127.0.0.1`；Compose 中使用 `--host 0.0.0.0` 监听容器网络，
宿主机仅映射 `127.0.0.1:7860:7860`。WebUI 校验访问主机和每次启动生成的请求令牌，
请使用启动时显示的地址，不要将其代理到公网。密钥仅从服务端 `.env` 读取。
MP4、JSON 记录和 `webui-任务ID.log` 均保存在输出目录，日志不会因刷新页面丢失。
页面按对象显示临时音频上传到 S3 的对象名、已传字节数和百分比，同时展示并发上传，扫描与边界复核每次上传分别计数；
进度条汇总已开始上传的对象，不代表尚未生成的音频或整个任务的总体进度；
进度来自 SDK 实际传输回调，传输达到 100% 后仍需等待服务确认，只有上传接口返回成功才标记完成。
上传失败会保留已传进度并明确报错；这不是浏览器上传视频或整个任务的总体进度。
同一标签页刷新会重新连接最近任务；服务重启不恢复任务状态，关闭服务会终止尚未完成的任务进程。

### Token 统计与费用估算

Token 统计仅保存在内存中，服务重启后丢失，不改变现有 manifest 记录。
价格依据用户提供的 2026-10-20 官网截图：`qwen3.8-flash` 和 `qwen3.8-omni-flash` 均为每百万 token
输入 0.8 元、缓存输入 0.1 元、输出 2.7 元。费用仅为估算，不含 S3 费用，也未计入免费额度或优惠。
未知模型或缺失 usage 时明确显示无法估价，不按零费用处理。

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

将视频放到 `input/`；输出保存在 `output/`。API 模式先填写 `.env`，启动 WebUI：

```bash
docker compose -f compose.api.yaml up --build -d
docker compose -f compose.api.yaml down

# 本地检测
docker compose -f compose.local.yaml build
docker compose -f compose.local.yaml run --rm local
docker compose -f compose.local.yaml down
```

API 模式启动后，浏览器打开 `http://127.0.0.1:7860`，输入容器内视频路径（如 `/input/input.mp4`），输出目录填写 `/output`。
`input/` 只读挂载到 `/input`，`output/` 挂载到 `/output`；默认输出目录由 `WEBUI_OUTPUT_DIR=/output` 设置。
Compose 通过 `MUSIC_AGENT_NETEASE_ENDPOINT=http://netease:3000/audio/match` 配置识曲接口。

两种配置均自动启动 NeteaseCloudMusicApi，健康检查通过后启动 WebUI 或本地检测，使用上述内部接口地址。
首次启动需要联网下载 npm 包；网易云服务不向宿主机开放端口，WebUI 端口仅向宿主机回环地址开放。

## Docker

```bash
docker build -t bili-music-segmenter .
docker build -f Dockerfile-gpu -t bili-music-segmenter:gpu .
docker run --rm -v "$PWD":/inaseg bili-music-segmenter uv run --frozen --group local inaseg.py --media input.mp4 --outdir output
```

GPU 镜像运行时增加 `--gpus all`，宿主机需安装 NVIDIA Container Toolkit。
