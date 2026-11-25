# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.building.datastruct import Tree


project = Path(SPEC).resolve().parent.parent
dependencies = Path(os.environ["TRACKER_MACOS_DEPENDENCIES"])

datas = [
    (str(project / "web" / "index.html"), "web"),
    (str(project / "web" / "app.js"), "web"),
    (str(project / "web" / "styles.css"), "web"),
    (str(project / "node_modules" / "cesium" / "Build" / "Cesium"), "node_modules/cesium/Build/Cesium"),
    (str(project / "LICENSE"), "."),
    (str(project / "examples" / "synthetic-track.kml"), "examples"),
    (str(dependencies / "third-party"), "third-party"),
]

dependency_trees = []
for directory in ("bin", "lib"):
    source = dependencies / directory
    if not source.exists():
        raise SystemExit(f"Missing staged dependency directory: {source}")
    dependency_trees.append(Tree(str(source), prefix=directory))

a = Analysis(
    [str(project / "gui_app.py")],
    pathex=[str(project)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "generate_from_config",
        "render_video",
        "compose_media_video",
        "mix_music",
        "prepare_track",
        "prepare_terrain",
        "prepare_imagery",
        "fitdecode",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngineWidgets",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="3D Tracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch="arm64",
)

collection = COLLECT(
    exe,
    a.binaries,
    a.datas,
    *dependency_trees,
    strip=False,
    upx=False,
    name="3D Tracker",
)

app = BUNDLE(
    collection,
    name="3D Tracker.app",
    icon=None,
    bundle_identifier="com.3dtrackmovie.app",
    info_plist={
        "CFBundleDisplayName": "3D Tracker",
        "CFBundleName": "3D Tracker",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "26.0",
        "NSHighResolutionCapable": True,
    },
)
