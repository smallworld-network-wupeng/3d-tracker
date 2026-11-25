# 3D 轨迹影片生成器

这是一个带中文桌面界面的轨迹视频工具。导入 FIT 或 Garmin 风格的 KML，在窗口里选择横屏或竖屏、时长和画质，就能把运动路线做成带 3D 地形的 MP4。还可以加入沿途实拍片段和背景音乐。

## 界面怎么用

1. 在 **活动信息** 中点击「选择文件」导入轨迹。活动名称默认取自文件名，可以修改。推荐使用 FIT，文件中有记录时可显示心率、海拔和实时配速。
2. 在 **影片设置** 中选横屏或竖屏、720P 或 1080P，再选影片时长。镜头距离会根据路线跨度、海拔和画幅自动调整。
3. 可以在 **素材** 中选择实拍影片文件夹，再点「编辑影片片段」。在弹窗里播放影片并标记起点和终点，同一个文件可以选多段。还可以修正拍摄时间，便于与轨迹对齐。修正会保存在 `video_segments.txt` 中。背景音乐也在这一区选择。
4. 在 **输出** 中选好保存位置，点「快速预览」检查路线和镜头，或点「生成影片」导出含所选素材的完整 MP4。生成完成后可点「打开影片」。

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

## 许可

项目源码和合成示例采用 [MIT 许可证](LICENSE)。CesiumJS、PySide6、FFmpeg 等依赖适用各自的许可。地图服务、瓦片及第三方媒体适用各自的授权条款。使用在线底图导出或发布视频前，请核对数据服务的使用和署名要求。
