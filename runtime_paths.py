"""Runtime paths shared by source and frozen macOS builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parent
IS_BUNDLED = bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT)).resolve()
_configured_work_root = os.environ.get("THREED_TRACKER_WORK_ROOT")
WORK_ROOT = (
    Path(_configured_work_root).expanduser()
    if _configured_work_root
    else Path.home() / "Library" / "Application Support" / "3DTrackMovie"
    if IS_BUNDLED and sys.platform == "darwin"
    else SOURCE_ROOT
)


def bundled_chromium() -> Path:
    return RESOURCE_ROOT / "chromium" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"


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
    return SOURCE_ROOT / "output"
