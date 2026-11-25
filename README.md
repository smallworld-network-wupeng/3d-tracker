# CesiumJS 轨迹视频

把 FIT（推荐）或 Garmin 风格 KML 轨迹渲染成可重复生成的 CesiumJS 3D 动画，再由 Python 驱动 Chrome 截帧、FFmpeg 合成 MP4。FIT 可同时提供 GPS、海拔、心率和实时配速。

## 环境

- Python 3.9 或更高版本（须有可用的 PySide6）
- Node.js 22.17 或更高版本，以及 npm
- 支持 WebGL 2 的 Google Chrome、Chromium 或 Microsoft Edge
- `PATH` 中可用的 `ffmpeg` 和 `ffprobe`，FFmpeg 需要支持 `libx264` 编码

建议使用项目自己的 Python 环境安装依赖：

```bash
python3 -m venv .venv
# macOS / Linux
.venv/bin/python -m pip install -r requirements.txt
# Windows
.venv\Scripts\python -m pip install -r requirements.txt
```

安装 CesiumJS：

```bash
npm ci
```

## 图形界面

启动“3D轨迹影片生成器”：

```bash
# macOS / Linux
.venv/bin/python gui_app.py
# Windows
.venv\Scripts\python gui_app.py
```

主界面只显示轨迹、活动名称、横竖屏、影片时长、720P/1080P、实拍片段、背景音乐和输出位置。
地形、镜头、编码和混音参数使用内置预设。选择影片文件夹后，可在“编辑影片片段”中修正影片开始拍摄时间，并为同一影片添加多个起止区间。修正时间作为项目覆盖值保存到 `video_segments.txt`，不会改写原始影片。旧版三列清单仍然兼容。
镜头距离会根据轨迹跨度、海拔、横竖画幅和当前已绘制的路线自动调整：紧凑路线自动拉近，长距离路线自动拉远，并保留画面安全边距。

## 命令行

在项目根目录用自带的合成 KML 生成一段 4 秒的演示视频。此示例跳过下载地形和卫星影像：

```bash
.venv/bin/python generate_from_config.py examples/video_project.json
```

结果保存在 `output/demo.mp4`。Windows 上把命令里的 `.venv/bin/python` 换成 `.venv\Scripts\python.exe`。

用自己的轨迹生成 20 秒、1080p、30fps 视频。请把 `my-activity.fit` 改成实际文件路径：

```bash
.venv/bin/python render_video.py my-activity.fit -o output/my-activity.mp4 \
  --name "我的活动"
```

只解析轨迹，生成浏览器使用的轻量 JSON：

```bash
.venv/bin/python prepare_track.py my-activity.fit -o web/track.json
```

KML 仍然兼容，但只有 FIT 会提供心率和设备记录的实时速度/配速。

## 配置驱动生成

可将 `examples/video_project.json` 复制到根目录作为 `video_project.json`，再填写轨迹路径和输出参数。配置中的相对路径以项目根目录为准。执行完整流程：

```bash
.venv/bin/python generate_from_config.py video_project.json
```

只生成轨迹底片或只重新合成实拍视频：

```bash
.venv/bin/python generate_from_config.py video_project.json --render-only
.venv/bin/python generate_from_config.py video_project.json --compose-only
.venv/bin/python generate_from_config.py video_project.json --mix-only
```

渲染按帧推进。启用在线底图时，程序会按轨迹覆盖范围向 AWS Terrain Tiles 和 Esri World Imagery 请求瓦片，并将地形和影像缓存到 `web/terrain/` 和 `web/imagery/`。FIT/KML 文件由本机读取。CLI 可使用 `--no-terrain --no-imagery` 跳过下载。

## 许可

项目源码和合成示例采用 [MIT 许可证](LICENSE)。CesiumJS、PySide6、FFmpeg 等依赖适用各自的许可。地图服务、瓦片及第三方媒体适用各自的授权条款。使用在线底图导出或发布视频前，请核对数据服务的使用和署名要求。
