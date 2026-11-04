# 网易云指纹识曲

`afp.js`、`afp.wasm.js` 与音频匹配逻辑来自 NeteaseCloudMusicApi。
`audio_match.js` 按 npm `NeteaseCloudMusicApi@4.32.0` 的 `module/audio_match.js`
提取并改为 Node.js 自带 fetch，直接调用上游音频匹配地址；不启动 HTTP 服务，
不安装 NeteaseCloudMusicApi 或 axios。发行包 SHA1：`7ab2ad102a0b7d2318695be13ae87737c3452ad9`。
保留 MIT 许可证见 LICENSE。

`generate_fp.js` 读取 FFmpeg 生成的 8 kHz 单声道 Float32 PCM 并生成指纹。
`audio_match.js` 从 stdin 读取指纹、时长、Cookie、超时，stdout 只返回 JSON。
需要 Node.js 20 或以上。上游错误、超时、非预期响应均显式失败。
