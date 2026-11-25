"""Collect licenses and matching source references from the build inputs."""

import importlib.metadata
import re
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parent.parent


def distribution_license(name: str, notices: Path) -> str:
    package = importlib.metadata.distribution(name)
    for file in package.files or ():
        if file.parent.name == "licenses":
            destination = notices / name / file.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(package.locate_file(file), destination)
    return package.version


def collect_notices(notices: Path, binaries: set[Path], ffmpeg: Path) -> None:
    notices.mkdir()
    formulas = {path.parent.parent for path in binaries}
    rows = []
    for keg in sorted(formulas):
        formula, = (keg / ".brew").glob("*.rb")
        contents = formula.read_text(encoding="utf-8")
        url = re.search(r'^  url "([^"]+)"', contents, re.MULTILINE)[1]
        revision = re.search(r'revision: "([a-f0-9]+)"', contents)
        if revision:
            url = f"{url.removesuffix('.git')}/-/archive/{revision[1]}/{formula.stem}-{revision[1]}.tar.gz"
        digest = re.search(r'^  sha256 "([a-f0-9]+)"', contents, re.MULTILINE)
        license_name = re.search(r'^  license "([^"]+)"', contents, re.MULTILINE)
        destination = notices / "Homebrew" / formula.stem
        destination.mkdir(parents=True)
        shutil.copy2(formula, destination)
        for file in keg.iterdir():
            if file.is_file() and file.name.upper().startswith(("LICENSE", "COPYING", "NOTICE", "PATENTS")):
                shutil.copy2(file, destination)
        rows.append(
            f"- {formula.stem} {keg.name} ({license_name[1] if license_name else 'see license'}): {url}"
            + (f" (SHA-256 `{digest[1]}`)" if digest else "")
        )

    with (notices / "Homebrew" / "ffmpeg-build.txt").open("w", encoding="utf-8") as output:
        subprocess.run([str(ffmpeg), "-L"], stdout=output, stderr=subprocess.STDOUT, check=True)
    python_license = Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "LICENSE.txt"
    shutil.copy2(python_license, notices / "Python-LICENSE.txt")
    fitdecode = distribution_license("fitdecode", notices)
    pyinstaller = distribution_license("pyinstaller", notices)
    qt = distribution_license("PySide6", notices)
    cesium_package = PROJECT / "node_modules" / "cesium"
    cesium = re.search(r'"version":\s*"([^"]+)"', (cesium_package / "package.json").read_text())[1]
    shutil.copy2(cesium_package / "LICENSE.md", notices / "Cesium-LICENSE.md")

    (notices / "SOURCE.md").write_text(
        f"""# Third-party software and source

The application's MIT license is included separately. The dependencies below
retain their own licenses. You may replace the dynamically linked LGPL
components with compatible modified builds and reverse engineer the application
as necessary to debug those changes. macOS requires affected code to be signed
again after changing app contents.

## Chromium

- Ungoogled Chromium 157.0.8103.78-1.1: https://github.com/ungoogled-software/ungoogled-chromium-macos/tree/157.0.8103.78-1.1
- Chromium source for 157.0.8103.78: https://chromium.googlesource.com/chromium/src/+/refs/tags/157.0.8103.78
- Binary replaced only at the signature level. See `Chromium-credits.html`
  for Chromium and bundled third-party notices.

## FFmpeg command-line tools and their dylibs

These binaries come from the Homebrew kegs below. The included formulas are the
build scripts from those kegs and identify any patches. The packaging script
changes Mach-O paths and signs the binaries. The FFmpeg build configuration is
recorded in `Homebrew/ffmpeg-build.txt`.

{chr(10).join(rows)}

## Qt multimedia, Python and JavaScript

- PySide6 and Shiboken {qt} (LGPL-3.0): https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-{qt}-src/
- Qt {qt} (LGPL-3.0 and third-party terms): https://download.qt.io/archive/qt/{qt.rsplit('.', 1)[0]}/{qt}/submodules/
- Qt Multimedia's FFmpeg n7.1.3 (LGPL): https://ffmpeg.org/releases/ffmpeg-7.1.3.tar.xz
- Python {sys.version.split()[0]}: https://www.python.org/ftp/python/{sys.version.split()[0]}/
- Fitdecode {fitdecode} (MIT): https://pypi.org/project/fitdecode/{fitdecode}/#files
- PyInstaller {pyinstaller} (GPL with bootloader exception): https://github.com/pyinstaller/pyinstaller/tree/v{pyinstaller}
- CesiumJS {cesium} (Apache-2.0 and third-party terms): https://github.com/CesiumGS/cesium/tree/{cesium}

The FFmpeg license files in `Homebrew/ffmpeg/` include the GPL and LGPL texts.
""",
        encoding="utf-8",
    )
