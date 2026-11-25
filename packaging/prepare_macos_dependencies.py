#!/usr/bin/env python3
"""Stage Chromium and a relocatable FFmpeg tree for the macOS bundle."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


SYSTEM_PREFIXES = ("/System/", "/usr/lib/")


def run(*command: str) -> str:
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout


def linked_libraries(path: Path) -> list[tuple[str, Path]]:
    lines = run("otool", "-L", str(path)).splitlines()[1:]
    install_id = run("otool", "-D", str(path)).splitlines()[1:]
    libraries = []
    for line in lines:
        name = line.strip().split(" (", 1)[0]
        if name in install_id or name.startswith(SYSTEM_PREFIXES):
            continue
        candidate = Path(name)
        if not candidate.is_absolute() or not candidate.is_file():
            raise RuntimeError(f"Cannot resolve {name} linked by {path}")
        libraries.append((name, candidate.resolve()))
    return libraries


def stage_ffmpeg(output: Path) -> set[Path]:
    bin_directory = output / "bin"
    lib_directory = output / "lib"
    bin_directory.mkdir(parents=True, exist_ok=True)
    lib_directory.mkdir(parents=True, exist_ok=True)

    executables = []
    for name in ("ffmpeg", "ffprobe"):
        source_name = shutil.which(name)
        if not source_name:
            raise FileNotFoundError(f"找不到 {name}")
        destination = bin_directory / name
        shutil.copy2(Path(source_name).resolve(), destination)
        executables.append(destination)

    pending = [source for executable in executables for _, source in linked_libraries(executable)]
    sources: dict[str, Path] = {}
    while pending:
        source = pending.pop()
        existing = sources.get(source.name)
        if existing:
            if existing != source:
                raise RuntimeError(f"动态库重名：{existing} / {source}")
            continue
        sources[source.name] = source
        pending.extend(dependency for _, dependency in linked_libraries(source))

    for name, source in sources.items():
        shutil.copy2(source, lib_directory / name)

    targets = [*executables, *(lib_directory / name for name in sources)]
    for target in targets:
        changes = []
        for original, source in linked_libraries(target):
            replacement = (
                f"@executable_path/../lib/{source.name}"
                if target.parent == bin_directory
                else f"@loader_path/{source.name}"
            )
            changes.extend(("-change", original, replacement))
        if target.parent == lib_directory:
            changes.extend(("-id", f"@loader_path/{target.name}"))
        if changes:
            subprocess.run(["install_name_tool", *changes, str(target)], check=True)
        subprocess.run(["codesign", "--force", "--sign", "-", str(target)], check=True)
    return {Path(shutil.which("ffmpeg")).resolve(), *sources.values()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    binaries = stage_ffmpeg(output)
    from collect_macos_notices import collect_notices

    collect_notices(output / "third-party", binaries, output / "bin" / "ffmpeg")


if __name__ == "__main__":
    main()
