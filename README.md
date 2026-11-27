# 3D Tracker · 3D 轨迹影片生成器

这是一个支持中英文桌面界面的轨迹视频工具。导入 FIT 或 Garmin 风格的 KML，在窗口里选择横屏或竖屏、时长和画质，就能把运动路线做成带 3D 地形的 MP4。还可以加入沿途实拍片段和背景音乐。

3D Tracker is an open-source desktop app for turning FIT and Garmin-style KML activity tracks into 3D route videos. Animate your route over terrain and satellite imagery, sync real footage by recording time, add music, and export a 720p or 1080p MP4 in landscape or portrait format.

[下载 macOS 版](#下载并安装-macos-版) · [下载 Windows 版](#下载并运行-windows-版) · [中文使用说明](#界面怎么用) · [English quick start](#english-quick-start)

## 下载并安装 macOS 版

适用于运行 **macOS 26 或更新版本的 Apple 芯片 Mac**。安装包已内置 Python、PySide6、CesiumJS、Chromium 和 FFmpeg。

1. 打开 [GitHub Releases](https://github.com/smallworld-network-wupeng/3d-tracker/releases)，在 `v0.1.0` 的 **Assets** 中下载 `3D-Tracker-0.1.0-macOS-arm64.zip`（约 236 MB）。
2. 双击 ZIP 解压，把 **3D Tracker.app** 拖到「应用程序」，再双击打开。
3. 此预览版使用临时签名，尚未经过 Apple 公证。如果 macOS 提示无法验证开发者，请先核对发布页上的 SHA-256，再参考 [Apple 的首次打开说明](https://support.apple.com/zh-cn/102445)。

初次试用可下载 [合成 KML 示例](https://raw.githubusercontent.com/smallworld-network-wupeng/3d-tracker/v0.1.0/examples/synthetic-track.kml)，在「活动信息」中导入。选 720P、设置时长和输出文件夹，再点「生成影片」。首次渲染新区域时需要联网下载地形和影像。

## 下载并运行 Windows 版

适用于 **Windows 10 或 11 x64**。ZIP 内已包含 Python、PySide6、CesiumJS、Chromium、FFmpeg 和照片处理依赖。

1. 在 [GitHub Releases](https://github.com/smallworld-network-wupeng/3d-tracker/releases) 找到 Windows x64 预览版，从 **Assets** 下载文件名以 `-windows-x64.zip` 结尾的安装包。
2. 右键 ZIP，选择「全部解压缩」。打开解压出的 **3D Tracker** 文件夹，双击 **3D Tracker.exe**，并保留同目录的文件和文件夹。
3. 在「活动信息」中选择自带的 `examples/synthetic-track.kml` 或自己的 FIT/KML，选好画质、时长和输出文件夹，再点「生成影片」。首次保存会要求选择 `.3dtrack` 项目文件的位置。生成结束后点「打开影片」。

首次渲染新区域需联网下载地形和影像。Windows 预览版未做代码签名，SmartScreen 可能会提示无法验证发布者。下载后可用 PowerShell 的 `Get-FileHash -Algorithm SHA256` 核对发布页上的 SHA-256。

## 成片演示 / Demo

[![峨眉山 27 公里速攀比赛三维轨迹记录影片 / Mount Emei 27K Speed Climb Race 3D Route Replay](https://i.ytimg.com/vi/IezjI8kOxuc/hqdefault.jpg)](https://youtu.be/IezjI8kOxuc)

[峨眉山 27 公里速攀比赛三维轨迹记录影片 / Mount Emei 27K Speed Climb Race · 3D Route Replay](https://youtu.be/IezjI8kOxuc)

## 界面怎么用

启动时会根据系统语言选择中文或英文。点击窗口右上角的「English」或「中文」即可切换。

1. 在 **活动信息** 中点击「选择文件」导入轨迹。活动名称默认取自文件名，可以修改。推荐使用 FIT，文件中有记录时可显示心率、海拔和实时配速。
2. 在 **影片设置** 中选横屏或竖屏、720P 或 1080P，再选影片时长。镜头距离会根据路线跨度、海拔和画幅自动调整。
3. 可以在 **素材** 中选择实拍影片文件夹，再点「编辑影片片段」。在弹窗里播放影片并标记起点和终点，同一个文件可以选多段。还可以修正拍摄时间，便于与轨迹对齐。背景音乐也在这一区选择，可设置影片开始后延迟多少秒播放。
4. 在 **素材** 中选择照片文件夹并点「编辑照片」。支持 JPG、JPEG、PNG、HEIC 和 HEIF。勾选要加入的照片，检查或修改 EXIF 拍摄时间，也可批量勾选活动时间内的照片。到达对应轨迹位置时，地图会暂停，照片默认显示 5 秒，再继续播放。活动时间外的照片可勾选「接在最后一个影片片段后」，它会紧接在最后播放的已选影片片段后，显示结束后继续轨迹。
5. 点击主窗口底部的「保存项目」保存 `.3dtrack` 文件。下次启动后点击同一位置的「打开项目…」（或按 `Ctrl/Cmd+O`），选择保存的项目文件即可继续编辑。轨迹、素材路径、视频剪辑、照片设置、音乐和影片参数都会保存在这一个项目文件中。项目目录内的素材使用相对路径，整个目录可以一起移动。
6. 在 **输出** 中选好保存位置，再点「生成影片」。程序会先保存项目，再导出 MP4。项目首次保存时需要选择文件位置。生成完成后可点「打开影片」。

照片拍摄时间统一以北京时间显示。带 EXIF 时区的照片会自动换算，缺少时区的照片可在编辑器里批量偏移，缺少拍摄时间的照片可手动填写。照片文件夹只扫描当前一层。

第一次试用时，可以在「轨迹文件」中选择仓库自带的 [合成 KML 示例](examples/synthetic-track.kml)。

## 从源码安装并启动 GUI

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

The desktop preview runs on **Apple Silicon Macs with macOS 26 or later**. Download `3D-Tracker-0.1.0-macOS-arm64.zip` (about 236 MB) under **Assets** for `v0.1.0` in [GitHub Releases](https://github.com/smallworld-network-wupeng/3d-tracker/releases). Unzip it, move **3D Tracker.app** to Applications, then open it. The preview is ad-hoc signed and is not notarized. If macOS cannot verify the developer, check the release's SHA-256 and refer to [Apple's first-launch instructions](https://support.apple.com/en-us/102445).

On **Windows 10 or 11 x64**, download the `-windows-x64.zip` asset from the Windows preview in [GitHub Releases](https://github.com/smallworld-network-wupeng/3d-tracker/releases). Choose **Extract All**, open the extracted **3D Tracker** folder, then start **3D Tracker.exe**. Keep the folder together. The included `examples/synthetic-track.kml` is ready to try. The Windows preview is unsigned. Check the release's SHA-256 if SmartScreen cannot verify its publisher.

To run from source, follow the [source installation instructions](#从源码安装并启动-gui).

The desktop interface starts in Chinese or English based on your system language. Use the **English** or **中文** button in the top-right corner to switch.

1. In **Activity**, click **Choose File** to import a FIT or Garmin-style KML file. You can try the bundled [synthetic KML track](examples/synthetic-track.kml). FIT recordings can also supply elevation, heart rate, and recorded pace when available.
2. In **Movie Settings**, choose landscape or portrait, a duration, and 720p or 1080p. The camera adjusts automatically to the route and frame.
3. In **Media**, you can choose a folder of footage and click **Edit Video Clips** to mark in and out points and align clips to the route by recording time. You can also choose background music and set how many seconds after the movie starts it should begin playing.
4. In **Media**, choose a photo folder and click **Edit Photos**. Check the JPEG, PNG, HEIC, or HEIF photos to include. Confirm or edit their EXIF capture times, shown in UTC+08. At each matching route position, the map pauses for the photo's display duration (5 seconds by default). Select **After Last Video Clip** to show a photo as soon as the last selected video clip finishes, then resume the route.
5. Click **Save Project** at the bottom of the main window to save a `.3dtrack` file. On a later launch, click **Open Project…** beside it (or press `Ctrl/Cmd+O`) and select the saved file to continue editing. The one project file contains the track and media paths, video clips, photo settings, music, and movie settings. Media inside the project directory uses relative paths so the directory can be moved as a unit.
6. In **Output**, choose a destination and click **Generate Movie**. The app saves the project before exporting the MP4 and asks for the project file location on the first save. When generation finishes, click **Open Movie** to watch the MP4.

The app reads track files locally. The first render for an uncached area needs internet access to fetch terrain and imagery tiles for the area covered by the route.

## 打包 macOS 版本

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
