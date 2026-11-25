# 3D Tracker · 3D 轨迹影片生成器

这是一个支持中英文桌面界面的轨迹视频工具。导入 FIT 或 Garmin 风格的 KML，在窗口里选择横屏或竖屏、时长和画质，就能把运动路线做成带 3D 地形的 MP4。还可以加入沿途实拍片段和背景音乐。

3D Tracker is an open-source desktop app for turning FIT and Garmin-style KML activity tracks into 3D route videos. Animate your route over terrain and satellite imagery, sync real footage by recording time, add music, and export a 720p or 1080p MP4 in landscape or portrait format.

[English quick start](#english-quick-start) · [中文使用说明](#界面怎么用)

## 成片演示 / Demo

[![峨眉山 27 公里速攀比赛三维轨迹记录影片 / Mount Emei 27K Speed Climb Race 3D Route Replay](https://i.ytimg.com/vi/IezjI8kOxuc/hqdefault.jpg)](https://youtu.be/IezjI8kOxuc)

[峨眉山 27 公里速攀比赛三维轨迹记录影片 / Mount Emei 27K Speed Climb Race · 3D Route Replay](https://youtu.be/IezjI8kOxuc)

## 界面怎么用

启动时会根据系统语言选择中文或英文。点击窗口右上角的「English」或「中文」即可切换。

1. 在 **活动信息** 中点击「选择文件」导入轨迹。活动名称默认取自文件名，可以修改。推荐使用 FIT，文件中有记录时可显示心率、海拔和实时配速。
2. 在 **影片设置** 中选横屏或竖屏、720P 或 1080P，再选影片时长。镜头距离会根据路线跨度、海拔和画幅自动调整。
3. 可以在 **素材** 中选择实拍影片文件夹，再点「编辑影片片段」。在弹窗里播放影片并标记起点和终点，同一个文件可以选多段。还可以修正拍摄时间，便于与轨迹对齐。修正会保存在 `video_segments.txt` 中。背景音乐也在这一区选择。
4. 在 **输出** 中选好保存位置，点「生成影片」导出含所选素材的完整 MP4。生成完成后可点「打开影片」。

第一次试用时，可以在「轨迹文件」中选择仓库自带的 [合成 KML 示例](examples/synthetic-track.kml)。

## 安装并启动 GUI

安装所需环境后，在项目根目录执行下方命令。

- Python 3.9 或更高版本（须有可用的 PySide6）
- Node.js 22.17 或更高版本，以及 npm
- 支持 WebGL 2 的 Google Chrome、Chromium 或 Microsoft Edge
- `PATH` 中可用的 `ffmpeg` 和 `ffprobe`，FFmpeg 需要支持 `libx264` 编码

**macOS / Linux**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci
.venv/bin/python gui_app.py
```

**Windows（PowerShell）**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd ci
.\.venv\Scripts\python.exe gui_app.py
```

首次生成时，程序会下载轨迹附近的地形和卫星影像，因此需要网络。FIT/KML 文件在本机读取。底图请求按轨迹覆盖范围向 AWS Terrain Tiles 和 Esri World Imagery 获取瓦片，并缓存到 `web/terrain/` 和 `web/imagery/`。

## English quick start

The app runs from source. Install Python 3.9+ with PySide6 support, Node.js 22.17+ with npm, a WebGL 2-capable Chrome, Chromium, or Edge browser, and FFmpeg with `libx264` encoding. Make sure `ffmpeg` and `ffprobe` are on your `PATH`. Then run the [installation commands for your OS](#安装并启动-gui) from the project directory to launch `gui_app.py`.

The desktop interface starts in Chinese or English based on your system language. Use the **English** or **中文** button in the top-right corner to switch.

1. In **Activity**, click **Choose File** to import a FIT or Garmin-style KML file. You can try the bundled [synthetic KML track](examples/synthetic-track.kml). FIT recordings can also supply elevation, heart rate, and recorded pace when available.
2. In **Movie Settings**, choose landscape or portrait, a duration, and 720p or 1080p. The camera adjusts automatically to the route and frame.
3. In **Media**, you can choose a folder of footage and click **Edit Video Clips** to mark in and out points and align clips to the route by recording time. You can also choose background music.
4. In **Output**, choose a destination and click **Generate Movie**. When it finishes, click **Open Movie** to watch the MP4.

The app reads track files locally. The first render for an uncached area needs internet access to fetch terrain and imagery tiles for the area covered by the route.

## 打包 macOS 版本

Apple Silicon 预览版可从 [GitHub Releases](https://github.com/smallworld-network-wupeng/3d-tracker/releases) 下载。应用内置 Python/PySide6、CesiumJS、FFmpeg/ffprobe 和 Chromium。当前二进制使用 macOS 26 构建的 Homebrew FFmpeg，要求 macOS 26 或更新版本。

本机构建需要已安装的 Homebrew FFmpeg，以及 [Ungoogled Chromium 157.0.8103.78-1.1 的 arm64 镜像](https://github.com/ungoogled-software/ungoogled-chromium-macos/releases/tag/157.0.8103.78-1.1)。挂载镜像后，将其中的 `Chromium.app` 路径传给构建脚本。第三方许可、构建配方和对应源码地址随应用附带。

```bash
.venv/bin/python -m pip install "pyinstaller>=6.10,<7"
./scripts/build_macos_release.sh "/path/to/Chromium.app"
```

输出为 `dist/3D Tracker.app` 和 `release/github/3D-Tracker-0.1.0-macOS-arm64.zip`。预览版使用临时（ad-hoc）签名，macOS Gatekeeper 可能会拦截首次打开。

<details>
<summary>命令行与批量生成</summary>

在项目根目录用自带的合成 KML 生成一段 4 秒的演示视频。此示例跳过下载地形和卫星影像：

```bash
.venv/bin/python generate_from_config.py examples/video_project.json
```

结果保存在 `output/demo.mp4`。Windows 上把命令里的 `.venv/bin/python` 换成 `.\.venv\Scripts\python.exe`。

用自己的轨迹生成 20 秒、1080p、30fps 视频。请把 `my-activity.fit` 改成实际文件路径：

```bash
.venv/bin/python render_video.py my-activity.fit -o output/my-activity.mp4 \
  --name "我的活动"
```

只解析轨迹，生成浏览器使用的轻量 JSON：

```bash
.venv/bin/python prepare_track.py my-activity.fit -o web/track.json
```

### 配置驱动生成

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

CLI 可使用 `--no-terrain --no-imagery` 跳过瓦片下载。

</details>

## 许可 / License

项目源码和合成示例采用 [MIT 许可证](LICENSE)。CesiumJS、PySide6、FFmpeg 等依赖适用各自的许可。地图服务、瓦片及第三方媒体适用各自的授权条款。使用在线底图导出或发布视频前，请核对数据服务的使用和署名要求。

The source code and synthetic example are under the [MIT License](LICENSE). Dependencies, map services, tiles, and third-party media are subject to their own terms. Check the applicable usage and attribution requirements before exporting or publishing videos with online basemaps.
