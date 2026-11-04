# bili-music-segmenter

以 API 服务分析直播录像、复核完整单曲边界并导出演唱片段。支持浏览器上传，以及 yt-dlp 下载视频后自动合并、切片。全部操作通过 Material 3 工具操作中心完成，任务由 Python 服务持久执行。

需要 Python 3.12、uv、FFmpeg、Node.js 20 或以上。项目不再包含本地检测模型、TensorFlow 或 GPU 镜像。网易云识曲直接运行随项目打包的 JavaScript，无需单独启动 NeteaseCloudMusicApi。

## 启动

```bash
cp .env.example .env
# 填写 API 与 S3 配置
uv sync --group api
uv run --group api -m segment.webui
```

使用控制台打印的带令牌地址打开页面。服务默认仅监听 `127.0.0.1:7860`；可用 `--port` 修改端口。令牌每次启动更换，服务重启后请使用新地址。浏览器保存令牌并从地址栏移除；普通 API 必须通过请求头认证，试听和下载链接支持 URL 令牌。

根目录 `.env` 必填：

```dotenv
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=
S3_ACCESS_KEY_ID=
S3_ACCESS_KEY_SECRET=
S3_ENDPOINT=
S3_BUCKET=
S3_REGION=
```

`DASHSCOPE_BASE_URL` 是与 API key 对应的 HTTPS 接入地址。音频模型默认 `qwen3.8-omni-flash`，文本与全场审核默认 `qwen3.8-flash`。S3 支持 AWS S3、MinIO、R2 等兼容存储；Endpoint 必须能被云端模型访问。Bucket 保持私有，授予指定前缀的上传、读取、HEAD 与删除权限。可配置 `S3_PREFIX`、`S3_ADDRESSING_STYLE`、`S3_USER_AGENT`，详见 `.env.example`。

## 工具操作中心

- **工作台**：选择或拖入音视频，调整执行顺序及参数，上传后提交任务。浏览器上传按实际传输字节显示进度，支持取消、移除和手动重试。同名文件使用独立 ID。
- **链接下载**：填入 yt-dlp 支持的视频链接，按需填写 Cookie 请求头，或读取 Netscape 格式的 `cookies.txt`，点击“下载、合并并切片”。服务负责下载音视频轨、合并封装为 MKV，再执行分析和切片。当前按单视频链接处理，不展开播放列表。下载字节数和合并状态显示在步骤列表中。
- **历史**：独立查看日志、步骤和结果；浏览历史时当前任务仍持续跟踪。手动选择视频后保持选择，可显式点击“跟随当前视频”。
- **用量**：查看本次服务统计、选中任务累计费用、各次执行和实际模型调用记录、按模型明细。任务用量跨服务重启保留，服务累计从本次启动计算。

结果支持页面试听、按片段下载，以及任务结束后下载包含确认片段与 JSON 记录的 ZIP。上传源文件、下载视频、结果、检查点及缓存保留至手动删除。下载 Cookie 仅存于源文件目录的权限 `0600` 文件，接口不返回 Cookie 内容，浏览器不保存 Cookie；删除最后引用的任务时一并清理。

任务与文件保存在 `data/webui/`，可用 `--data-dir` 或 `WEBUI_DATA_DIR` 指定：

| 位置 | 内容 |
| --- | --- |
| `workspace.sqlite3` | 文件、任务、执行次数、结构化步骤、用量及缓存引用 |
| `uploads/<id>/` | 上传或下载源文件，以及下载参数 |
| `jobs/<id>/<视频ID>/` | JSON 记录、片段、检查点、执行日志 |
| `audio/` | 按内容定位的共享提取音频 |

服务运行不依赖页面保持打开。服务重启后未完成任务标记为“执行中断”，点击续跑恢复。旧版 `logs/webui-history.json` 导入为仅摘要的历史记录，会明确提示缺失详情与源文件。

## 进度、重试与缓存

进度由独立事件管道传输：批次按视频计数，扫描按分块计数，候选按工作单元计数，FFmpeg 按已处理媒体时长计数，浏览器和 S3 上传分别按真实字节计数。未知总量的请求展示状态与耗时，不以固定阶段权重估算时间百分比。并行步骤可同时运行，等待资源、缓存复用、跳过、失败和停止分别展示。

“续跑”保持任务与参数，复用该任务通过校验的成功检查点，仅执行未完成步骤和依赖改变的后续工作。“重新处理”创建新任务，允许调整参数，重新生成模型分析，同时复用匹配的媒体缓存。语义校验失败的模型响应不会提交为成功检查点。

同一音频窗口按源文件摘要、精确区间、编码参数及提取版本定位。模型请求前验证 S3 对象并重新签名；已删除的对象明确记录缓存未命中并重新提取上传，权限或网络错误直接失败。成功和失败任务均保留缓存，手动删除任务时仅删除不再被其他任务引用的对象。删除失败保留“清理未完成”和错误，可再次清理。

边界复核以完整演唱为目标，保留有证据的前奏、尾奏、间奏、换气与短暂插话。触及输入边界时按证据扩张上下文；全场审核只请求需要的追加音频复核，最终确认后才导出。复核失败会停止依赖步骤并保留已确认结果，不悄悄使用旧边界继续导出。模型判断仍可能不准确，JSON 记录保留分析依据。

## 并发与耗时

视频按队列顺序执行，同一视频内部的独立分块、候选与追加复核并发。Shazam 与网易云在同一运行事件循环中并发；阻塞的 FFmpeg、S3、同步模型与网易云工具调用在工作线程执行。音频提取和导出共享媒体资源额度，S3 SDK 不再额外开启隐藏传输线程。候选结果由单一协调器按稳定顺序提交 JSON。

| 参数 | 默认 |
| --- | --- |
| 扫描并发 | 3 |
| 候选处理并发 | 3 |
| 模型请求并发 | 3 |
| 识曲请求并发 | 3 |
| S3 上传并发 | 2 |
| 媒体进程并发 | CPU 数与 2 的较小值 |

前端高级设置可调整额度及分块时长。每步记录实际耗时、等待资源耗时和复用状态；调用与上传记录可用于对照串行设置。单视频速度取决于媒体长度、CPU、网络和上游响应，不能仅凭调度并发数推断收益。

所有实际模型请求（包括失败及 JSON 重试）都记账；检查点复用不产生新调用。无效 JSON 默认额外重试 3 次，可通过 `MUSIC_AGENT_JSON_RETRIES=0` 禁用；请求失败明确结束，不隐藏错误。费用沿用项目已有价格表，仅为估算，未知价格或缺失 usage 会标记统计不完整，不含 S3 费用。

## 网易云识曲

`vendor/ncm-afp/audio_match.js` 从 NeteaseCloudMusicApi 4.32.0 的音频匹配路由提取，使用 Node 自带 fetch 直接请求网易云上游，不依赖 axios、Web 服务器或整包 npm 安装。来源和 MIT 许可见同目录 README 与 LICENSE。

Python 提取 8 kHz Float32 PCM，打包的指纹工具生成 audioFP，再通过标准输入向匹配工具传递指纹、超时和 Cookie。无匹配、异常响应、HTTP 错误和超时分别明确处理。可通过服务端 `MUSIC_AGENT_NETEASE_COOKIE` 配置网易云 Cookie，与下载视频的 Cookie 独立。

## 界面与构建

固定使用 `@material/web@2.5.0`。按钮、图标按钮、列表使用该版本 `labs/gb` 的 Expressive 工具实现；输入、开关、标签页、进度条与对话框使用 M3 组件。蓝紫主题由 `#3f5ad4` 生成，浅深色均使用本地字体与 SVG 图标，无外部字体请求。

桌面达到 1280px 时三栏，840–1279px 双栏，更窄时单栏及面板标签；手机使用底部导航。键盘可通过 Tab 操作，`Alt+1/2/3` 切换区域，系统减少动态效果模式取消位移。

```bash
cd webui
npm ci
node scripts/theme.mjs   # 需要重新生成主题时使用
npm run typecheck
npm run release         # 正式构建并复制到 segment/webui_dist
```

Python 直接托管静态产物，运行时不需要 Next.js 服务。发布产物随仓库保留。

## 命令行与 Docker

```bash
uv run --group api -m segment.music_agent.cli --media video.mp4 --outdir output
uv run --group api -m segment.music_agent.cli --help

docker compose -f compose.api.yaml up --build -d
docker compose -f compose.api.yaml logs api
```

Compose 仅启动一个应用容器，挂载 `data/webui/` 和 `logs/`，不需要单独的网易云容器。控制台日志提供带令牌地址；停止容器不删除持久化数据。CLI 与 WebUI 共用 API 管线和后端环境配置。

## 开发验证

```bash
uv sync --group api --group dev
ruff check .
ruff format --check .
timeout 60s uv run --group api --group dev -m pytest -q
npm --prefix webui run typecheck
npm --prefix webui run release
```

后端测试覆盖任务和上传持久化、停止进程组、分块并发、检查点、S3 引用清理、下载与 Cookie 处理、网易云提取工具、真实 FFmpeg 提取与导出。外部模型、S3 与网站账户的真实链路需要有效服务配置。
