"""Runtime paths shared by source and frozen desktop builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parent
IS_BUNDLED = bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT)).resolve()
_configured_work_root = os.environ.get("THREED_TRACKER_WORK_ROOT")

if _configured_work_root:
    WORK_ROOT = Path(_configured_work_root).expanduser().resolve()
elif IS_BUNDLED and sys.platform == "darwin":
    WORK_ROOT = Path.home() / "Library" / "Application Support" / "3DTrackMovie"
elif IS_BUNDLED and sys.platform == "win32":
    local_data = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    WORK_ROOT = Path(local_data) / "3DTrackMovie"
else:
    WORK_ROOT = SOURCE_ROOT


def bundled_chromium() -> Path:
    if sys.platform == "win32":
        return RESOURCE_ROOT / "chromium" / "chrome.exe"
    return RESOURCE_ROOT / "chromium" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"


def render_worker_executable() -> str:
    if IS_BUNDLED and sys.platform == "win32":
        return str(Path(sys.executable).with_name("3D Tracker Worker.exe"))
    return sys.executable


def configure_runtime_environment() -> None:
    """Make packaged command-line helpers discoverable by subprocesses."""

    if not IS_BUNDLED:
        return
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    binary_directory = RESOURCE_ROOT / "bin"
    os.environ["PATH"] = os.pathsep.join((str(binary_directory), os.environ.get("PATH", "")))


def default_output_directory() -> Path:
    if IS_BUNDLED and sys.platform == "darwin":
        return Path.home() / "Movies" / "3D Tracker"
    if IS_BUNDLED and sys.platform == "win32":
        return Path.home() / "Videos" / "3D Tracker"
    return SOURCE_ROOT / "output"
