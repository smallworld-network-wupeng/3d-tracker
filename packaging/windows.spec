import os
from pathlib import Path

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_data_files, collect_delvewheel_libs_directory


project = Path(SPEC).resolve().parent.parent
dependencies = Path(os.environ["TRACKER_WINDOWS_DEPENDENCIES"])
heif_data, heif_libraries = collect_delvewheel_libs_directory("pillow_heif")
analysis = Analysis(
    [str(project / "gui_app.py")],
    pathex=[str(project)],
    datas=[
        (str(project / "web" / name), "web")
        for name in ("index.html", "app.js", "styles.css")
    ] + [
        (str(project / "node_modules/cesium/Build/Cesium"), "node_modules/cesium/Build/Cesium"),
        (str(project / "LICENSE"), "."),
        (str(project / "examples/synthetic-track.kml"), "examples"),
    ] + heif_data + collect_data_files("tzdata"),
    binaries=heif_libraries,
    hiddenimports=["generate_from_config", "render_video", "compose_media_video", "mix_music", "tzdata"],
)
pyz = PYZ(analysis.pure)

app = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="3D Tracker", console=False, upx=False)
# Keep a console bootloader for child processes so the GUI can capture progress and errors.
worker = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="3D Tracker Worker", console=True, upx=False)

COLLECT(
    app,
    worker,
    analysis.binaries,
    analysis.datas,
    *(Tree(str(dependencies / name), prefix=name) for name in ("bin", "chromium", "third-party")),
    name="3D Tracker",
    upx=False,
)
