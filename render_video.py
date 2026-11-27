#!/usr/bin/env python3
"""Drive headless Chrome via CDP, capture deterministic Cesium frames, encode MP4."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from prepare_track import prepare
from prepare_terrain import prepare_terrain
from prepare_imagery import prepare_imagery
from runtime_paths import IS_BUNDLED, RESOURCE_ROOT, WORK_ROOT, bundled_chromium, configure_runtime_environment


configure_runtime_environment()
ROOT = RESOURCE_ROOT
WEB_ROOT = WORK_ROOT / "web"


class StaticHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".wasm": "application/wasm",
        ".css": "text/css",
        ".json": "application/json",
    }

    def translate_path(self, path: str) -> str:
        relative = urlparse(path).path.lstrip("/")
        if relative.startswith("cesium/"):
            return str(ROOT / "node_modules" / "cesium" / "Build" / "Cesium" / relative.removeprefix("cesium/"))
        if relative in {"track.json", "render-config.json"} or relative.startswith(("terrain/", "imagery/")):
            return str(WEB_ROOT / relative)
        return str(ROOT / "web" / (relative or "index.html"))

    def log_message(self, _format: str, *args) -> None:
        pass


class CDP:
    """Small dependency-free WebSocket client sufficient for Chrome DevTools Protocol."""

    def __init__(self, websocket_url: str):
        target = urlparse(websocket_url)
        self.sock = socket.create_connection((target.hostname, target.port), timeout=30)
        self.sock.settimeout(180)
        key = base64.b64encode(os.urandom(16)).decode()
        request_target = target.path + (f"?{target.query}" if target.query else "")
        request = (
            f"GET {request_target} HTTP/1.1\r\n"
            f"Host: {target.hostname}:{target.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode())
        response = self._recv_until(b"\r\n\r\n")
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"WebSocket 握手失败: {response[:200]!r}")
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if accept not in response:
            raise RuntimeError("WebSocket 握手校验失败")
        self.next_id = 1
        self.pending = {}

    def _recv_until(self, marker: bytes) -> bytes:
        data = b""
        while marker not in data:
            data += self.sock.recv(4096)
        return data

    def _read_exact(self, length: int) -> bytes:
        chunks = []
        remaining = length
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise EOFError("Chrome CDP connection closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _receive(self) -> dict:
        fragments = []
        while True:
            first, second = self._read_exact(2)
            opcode, length = first & 0x0F, second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            masked = bool(second & 0x80)
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length)
            if masked:
                payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
            if opcode == 0x9:
                self._send_frame(payload, opcode=0xA)
                continue
            if opcode == 0x8:
                raise EOFError("Chrome closed the WebSocket")
            fragments.append(payload)
            if first & 0x80:
                return json.loads(b"".join(fragments))

    def _send_frame(self, payload: bytes, opcode: int = 0x1) -> None:
        mask = os.urandom(4)
        length = len(payload)
        header = bytearray([0x80 | opcode])
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def call(self, method: str, params: Optional[dict] = None) -> dict:
        request_id = self.next_id
        self.next_id += 1
        self._send_frame(json.dumps({"id": request_id, "method": method, "params": params or {}}).encode())
        while True:
            message = self._receive()
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method}: {message['error']}")
                return message.get("result", {})
            if "id" in message:
                self.pending[message["id"]] = message

    def close(self) -> None:
        try:
            self._send_frame(b"", opcode=0x8)
        finally:
            self.sock.close()


def find_chrome() -> str:
    if IS_BUNDLED:
        executable = bundled_chromium()
        if executable.is_file():
            return str(executable)
        raise FileNotFoundError("Bundled Chromium is missing.")
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chrome"),
        shutil.which("msedge"),
    ]
    for environment_name, relative_paths in {
        "PROGRAMFILES": [
            "Google/Chrome/Application/chrome.exe",
            "Microsoft/Edge/Application/msedge.exe",
        ],
        "PROGRAMFILES(X86)": [
            "Google/Chrome/Application/chrome.exe",
            "Microsoft/Edge/Application/msedge.exe",
        ],
        "LOCALAPPDATA": [
            "Google/Chrome/Application/chrome.exe",
            "Microsoft/Edge/Application/msedge.exe",
        ],
    }.items():
        base = os.environ.get(environment_name)
        if base:
            candidates.extend(str(Path(base) / relative_path) for relative_path in relative_paths)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise FileNotFoundError("找不到 Google Chrome、Chromium 或 Microsoft Edge")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_json(url: str, timeout: float = 20) -> list[dict]:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return json.load(response)
        except Exception as error:
            last_error = error
            time.sleep(0.1)
    raise TimeoutError(f"等待 Chrome 超时: {last_error}")


def evaluate(cdp: CDP, expression: str, await_promise: bool = False):
    result = cdp.call("Runtime.evaluate", {
        "expression": expression,
        "awaitPromise": await_promise,
        "returnByValue": True,
    })
    if result.get("exceptionDetails"):
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False))
    return result.get("result", {}).get("value")


def render(args) -> None:
    if not (ROOT / "node_modules" / "cesium" / "Build" / "Cesium" / "Cesium.js").exists():
        raise FileNotFoundError("缺少 CesiumJS。请先运行 npm install")
    WEB_ROOT.mkdir(parents=True, exist_ok=True)
    metadata = prepare(
        args.track.resolve(), WEB_ROOT / "track.json", args.sample_seconds,
        args.simplify_meters, args.name,
    )
    browser_config = {
        "fps": args.fps,
        "terrain_exaggeration": args.terrain_exaggeration,
        "imagery_margin_deg": args.imagery_margin_deg,
        "intro_ratio": args.intro_ratio,
        "outro_ratio": args.outro_ratio,
        "camera_pitch_deg": args.camera_pitch_deg,
        "camera_range_m": args.camera_range_m,
        "auto_camera_range": args.auto_camera_range,
        "camera_min_range_m": args.camera_min_range_m,
        "camera_max_range_m": args.camera_max_range_m,
        "camera_fit_horizontal": args.camera_fit_horizontal,
        "camera_fit_vertical": args.camera_fit_vertical,
        "camera_fit_padding": args.camera_fit_padding,
        "camera_screen_y": args.camera_screen_y,
        "camera_look_ahead_m": args.camera_look_ahead_m,
        "camera_target_lead": args.camera_target_lead,
        "orbit_start_deg": args.orbit_start_deg,
        "orbit_degrees": args.orbit_degrees,
        "overview_heading_deg": args.overview_heading_deg,
        "overview_pitch_deg": args.overview_pitch_deg,
        "overview_min_range_m": args.overview_min_range_m,
        "overview_range_scale": args.overview_range_scale,
        "overview_start_scale": args.overview_start_scale,
        "overview_end_scale": args.overview_end_scale,
        "overview_distance_scale": args.overview_distance_scale,
        "final_orbit_degrees": args.final_orbit_degrees,
        "final_pitch_deg": args.final_pitch_deg,
        "final_range_scale": args.final_range_scale,
        "metric_scale": args.metric_scale,
        "portrait_profile_width": args.portrait_profile_width,
        "landscape_title_width": args.landscape_title_width,
    }
    (WEB_ROOT / "render-config.json").write_text(
        json.dumps(browser_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"轨迹: {metadata['name']} | {metadata['raw_point_count']} 原始点 → "
        f"{metadata['sampled_point_count']} 抽样点 → {metadata['point_count']} 渲染点"
    )
    if not args.no_terrain:
        terrain = prepare_terrain(metadata["bounds"], WEB_ROOT / "terrain", args.terrain_max_level)
        print(f"SRTM 地形: {terrain['tile_count']} 瓦片，最高层级 {terrain['max_level']}")
    if not args.no_imagery:
        imagery = prepare_imagery(metadata["bounds"], WEB_ROOT / "imagery", 8, args.imagery_max_level)
        print(f"Esri 影像: {imagery['tile_count']} 瓦片，层级 8–{imagery['max_level']}")

    server_port = free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", server_port), StaticHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    chrome_port = free_port()
    frame_count = max(2, round(args.seconds * args.fps))
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cesium-video-") as temp:
        temp_path = Path(temp)
        frames = temp_path / "frames"
        frames.mkdir()
        browser_flags = []
        if sys.platform == "win32":
            # Allow WebGL on machines where the driver cannot provide it.
            browser_flags.append("--enable-unsafe-swiftshader")
            if os.environ.get("THREED_TRACKER_SOFTWARE_WEBGL") == "1":
                browser_flags.append("--use-angle=swiftshader")
        browser_log_path = temp_path / "chromium.log"
        browser_flags.extend(("--enable-logging=stderr", "--log-level=1"))
        with browser_log_path.open("wb") as browser_log:
            chrome = subprocess.Popen([
                find_chrome(), "--headless=new", f"--remote-debugging-port={chrome_port}",
                f"--user-data-dir={temp_path / 'chrome'}", "--remote-allow-origins=*",
                "--hide-scrollbars", "--mute-audio", "--no-first-run", "--no-default-browser-check",
                "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                *browser_flags,
                f"--window-size={args.width},{args.height}", "about:blank",
            ], stdout=subprocess.DEVNULL, stderr=browser_log)
        cdp = None
        try:
            targets = wait_json(f"http://127.0.0.1:{chrome_port}/json/list")
            page = next(item for item in targets if item.get("type") == "page")
            cdp = CDP(page["webSocketDebuggerUrl"])
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            cdp.call("Page.bringToFront")
            cdp.call("Emulation.setDeviceMetricsOverride", {
                "width": args.width, "height": args.height, "deviceScaleFactor": 1, "mobile": False,
            })
            navigation = cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{server_port}/index.html"})
            if navigation.get("errorText"):
                raise RuntimeError(f"Chromium 无法打开本地渲染页面: {navigation['errorText']}")
            startup_seconds = 90 if sys.platform == "win32" else 45
            deadline = time.monotonic() + startup_seconds
            while time.monotonic() < deadline:
                error = evaluate(cdp, "window.__TRACK_ERROR__ || null")
                if error:
                    raise RuntimeError(error)
                render_error = evaluate(cdp, "window.__RENDER_ERROR__ || null")
                if render_error:
                    raise RuntimeError(f"Cesium 渲染失败: {render_error}")
                if evaluate(cdp, "window.__TRACK_READY__ === true"):
                    break
                time.sleep(0.1)
            else:
                state = evaluate(cdp, """({
                    page: document.readyState,
                    visibility: document.visibilityState,
                    cesium: typeof Cesium,
                    renderer: typeof window.renderFrame,
                    camera: Boolean(window.__CAMERA_FIT__),
                    resources: performance.getEntriesByType('resource').length
                })""")
                raise TimeoutError(f"Cesium 页面 {startup_seconds} 秒内未就绪: {state}")
            terrain_tiles = evaluate(cdp, "window.__TERRAIN_TILE_COUNT__ || 0")
            print(f"Cesium 已解码地形瓦片: {terrain_tiles}", flush=True)

            started = time.monotonic()
            for index in range(frame_count):
                evaluate(cdp, f"window.renderFrame({index}, {frame_count})", await_promise=True)
                render_error = evaluate(cdp, "window.__RENDER_ERROR__ || null")
                if render_error:
                    raise RuntimeError(f"Cesium 渲染失败（第 {index + 1} 帧）: {render_error}")
                screenshot = cdp.call("Page.captureScreenshot", {
                    "format": "jpeg", "quality": args.jpeg_quality, "fromSurface": True,
                })
                (frames / f"frame_{index:06d}.jpg").write_bytes(base64.b64decode(screenshot["data"]))
                if index == 0 or (index + 1) % max(1, args.fps * 2) == 0 or index + 1 == frame_count:
                    elapsed = time.monotonic() - started
                    print(f"截帧 {index + 1}/{frame_count} ({(index + 1) / frame_count:.0%})，已用 {elapsed:.1f}s", flush=True)

            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "warning", "-framerate", str(args.fps),
                "-i", str(frames / "frame_%06d.jpg"), "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p",
                "-c:v", "libx264", "-preset", args.preset, "-color_range", "tv",
                "-crf", str(args.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
            ], check=True)
        except Exception:
            browser_lines = browser_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if browser_lines:
                print("\n".join(browser_lines[-18:]), file=sys.stderr, flush=True)
            raise
        finally:
            if cdp:
                cdp.close()
            chrome.terminate()
            try:
                chrome.wait(timeout=5)
            except subprocess.TimeoutExpired:
                chrome.kill()
            server.shutdown()
    print(f"完成: {output} ({output.stat().st_size / 1024 / 1024:.1f} MiB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("track", type=Path, help="FIT 或 KML 轨迹文件")
    parser.add_argument("-o", "--output", type=Path, default=Path("output/track.mp4"))
    parser.add_argument("--seconds", type=float, default=20.0, help="输出视频时长")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--sample-seconds", type=float, default=5.0)
    parser.add_argument("--simplify-meters", type=float, default=2.0, help="绘制线的平面简化容差")
    parser.add_argument("--name", help="覆盖活动名称")
    parser.add_argument("--terrain-max-level", type=int, default=14)
    parser.add_argument("--terrain-exaggeration", type=float, default=1.35)
    parser.add_argument("--no-terrain", action="store_true", help="使用椭球地表，不加载 SRTM DEM")
    parser.add_argument("--imagery-max-level", type=int, default=14)
    parser.add_argument("--imagery-margin-deg", type=float, default=0.15)
    parser.add_argument("--no-imagery", action="store_true", help="不加载本地 Esri World Imagery")
    parser.add_argument("--intro-ratio", type=float, default=0.07)
    parser.add_argument("--outro-ratio", type=float, default=0.07)
    parser.add_argument("--camera-pitch-deg", type=float, default=-57.0)
    parser.add_argument("--camera-range-m", type=float, default=9500.0)
    camera_range_group = parser.add_mutually_exclusive_group()
    camera_range_group.add_argument("--auto-camera-range", dest="auto_camera_range", action="store_true")
    camera_range_group.add_argument("--no-auto-camera-range", dest="auto_camera_range", action="store_false")
    parser.set_defaults(auto_camera_range=True)
    parser.add_argument("--camera-min-range-m", type=float)
    parser.add_argument("--camera-max-range-m", type=float, default=120000.0)
    parser.add_argument("--camera-fit-horizontal", type=float)
    parser.add_argument("--camera-fit-vertical", type=float)
    parser.add_argument("--camera-fit-padding", type=float, default=1.10)
    parser.add_argument("--camera-screen-y", type=float)
    parser.add_argument("--camera-look-ahead-m", type=float, default=500.0)
    parser.add_argument("--camera-target-lead", type=float, default=0.65)
    parser.add_argument("--orbit-start-deg", type=float, default=18.0)
    parser.add_argument("--orbit-degrees", type=float, default=70.0)
    parser.add_argument("--overview-heading-deg", type=float, default=18.0)
    parser.add_argument("--overview-pitch-deg", type=float, default=-45.0)
    parser.add_argument("--overview-min-range-m", type=float, default=18000.0)
    parser.add_argument("--overview-range-scale", type=float, default=1.0)
    parser.add_argument("--overview-start-scale", type=float, default=1.16)
    parser.add_argument("--overview-end-scale", type=float, default=1.0)
    parser.add_argument("--overview-distance-scale", type=float, default=1.12)
    parser.add_argument("--final-orbit-degrees", type=float, default=180.0)
    parser.add_argument("--final-pitch-deg", type=float, default=-72.0)
    parser.add_argument("--final-range-scale", type=float, default=1.18)
    parser.add_argument("--metric-scale", type=float, default=1.0)
    parser.add_argument("--portrait-profile-width", type=float, default=520.0)
    parser.add_argument("--landscape-title-width", type=float, default=460.0)
    parser.add_argument("--jpeg-quality", type=int, default=94)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="medium")
    render(parser.parse_args())


if __name__ == "__main__":
    main()
