#!/usr/bin/env python3
"""Run the FIT/Cesium/media pipeline from one GUI-friendly JSON configuration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from runtime_paths import IS_BUNDLED, RESOURCE_ROOT, WORK_ROOT, configure_runtime_environment


configure_runtime_environment()
ROOT = RESOURCE_ROOT


def add_options(command: list[str], values: dict, mapping: dict[str, str]) -> None:
    for key, flag in mapping.items():
        if key in values and values[key] is not None:
            command.extend([flag, str(values[key])])


def display(command: list[str]) -> str:
    return " ".join(json.dumps(part, ensure_ascii=False) if any(char.isspace() for char in part) else part for part in command)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, nargs="?", default=Path("video_project.json"))
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--compose-only", action="store_true")
    parser.add_argument("--mix-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="只显示命令，不执行")
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    track = config["track"]
    render = config["render"]
    media = config.get("media", {})
    music = config.get("music", {})
    python = config.get("python", sys.executable)

    def entrypoint(script: str, bundled_flag: str) -> list[str]:
        if IS_BUNDLED:
            return [sys.executable, bundled_flag]
        return [python, str(ROOT / script)]

    render_command = [*entrypoint("render_video.py", "--render-video"), str(track["file"]), "-o", str(render["output"])]
    if track.get("name"):
        render_command.extend(["--name", str(track["name"])])
    add_options(render_command, track, {
        "sample_seconds": "--sample-seconds", "simplify_meters": "--simplify-meters",
    })
    add_options(render_command, render, {
        "seconds": "--seconds", "fps": "--fps", "width": "--width", "height": "--height",
        "terrain_max_level": "--terrain-max-level", "terrain_exaggeration": "--terrain-exaggeration",
        "imagery_max_level": "--imagery-max-level", "imagery_margin_deg": "--imagery-margin-deg",
        "intro_ratio": "--intro-ratio", "outro_ratio": "--outro-ratio",
        "camera_pitch_deg": "--camera-pitch-deg", "camera_range_m": "--camera-range-m",
        "camera_min_range_m": "--camera-min-range-m", "camera_max_range_m": "--camera-max-range-m",
        "camera_fit_horizontal": "--camera-fit-horizontal", "camera_fit_vertical": "--camera-fit-vertical",
        "camera_fit_padding": "--camera-fit-padding", "camera_screen_y": "--camera-screen-y",
        "camera_look_ahead_m": "--camera-look-ahead-m", "camera_target_lead": "--camera-target-lead",
        "orbit_start_deg": "--orbit-start-deg", "orbit_degrees": "--orbit-degrees",
        "overview_heading_deg": "--overview-heading-deg", "overview_pitch_deg": "--overview-pitch-deg",
        "overview_min_range_m": "--overview-min-range-m", "overview_range_scale": "--overview-range-scale",
        "overview_start_scale": "--overview-start-scale", "overview_end_scale": "--overview-end-scale",
        "overview_distance_scale": "--overview-distance-scale", "jpeg_quality": "--jpeg-quality",
        "final_orbit_degrees": "--final-orbit-degrees", "final_pitch_deg": "--final-pitch-deg",
        "final_range_scale": "--final-range-scale",
        "metric_scale": "--metric-scale",
        "portrait_profile_width": "--portrait-profile-width",
        "landscape_title_width": "--landscape-title-width",
        "crf": "--crf", "preset": "--preset",
    })
    render_command.append(
        "--auto-camera-range" if render.get("auto_camera_range", True) else "--no-auto-camera-range"
    )
    if render.get("no_terrain"):
        render_command.append("--no-terrain")
    if render.get("no_imagery"):
        render_command.append("--no-imagery")

    compose_command = [
        *entrypoint("compose_media_video.py", "--compose-media-video"), "--base", str(render["output"]),
        "--base-seconds", str(render["seconds"]), "--track-json", str(WORK_ROOT / "web" / "track.json"),
        "--render-config", str(WORK_ROOT / "web" / "render-config.json"),
        "--project-config", str(config_path),
        "--output", str(media.get("output", "output/final.mp4")),
        "--report", str(media.get("report", "output/media-events.json")),
        "--fps", str(render["fps"]),
    ]
    for key, flag in (
        ("directory", "--media-dir"), ("photo_directory", "--photo-dir"),
    ):
        if media.get(key):
            compose_command.extend([flag, str(media[key])])
    add_options(compose_command, media, {
        "group_window_seconds": "--group-window", "popup_width": "--popup-width",
        "popup_height": "--popup-height", "popup_border": "--popup-border",
        "popup_y": "--popup-y",
        "background_brightness": "--background-brightness",
        "popup_background_advance": "--popup-background-advance",
    })

    music_input = media.get("output") if media.get("enabled", False) else render["output"]
    music_command = [
        *entrypoint("mix_music.py", "--mix-music"), "--video", str(music_input),
        "--music", str(music.get("file", "")),
        "--output", str(music.get("output", "output/final-with-music.mp4")),
    ]
    add_options(music_command, music, {
        "target_lufs": "--target-lufs", "music_volume": "--music-volume",
        "start_offset_seconds": "--start-offset-seconds",
        "duck_threshold": "--duck-threshold", "duck_ratio": "--duck-ratio",
        "duck_attack_ms": "--duck-attack-ms", "duck_release_ms": "--duck-release-ms",
        "fade_in_seconds": "--fade-in-seconds", "fade_out_seconds": "--fade-out-seconds",
        "audio_bitrate": "--audio-bitrate",
    })

    commands = []
    if args.mix_only:
        if music.get("enabled", False):
            commands.append(music_command)
    elif args.render_only:
        commands.append(render_command)
    elif args.compose_only:
        if media.get("enabled", False):
            commands.append(compose_command)
        if music.get("enabled", False):
            commands.append(music_command)
    else:
        commands.append(render_command)
        if media.get("enabled", False):
            commands.append(compose_command)
        if music.get("enabled", False):
            commands.append(music_command)
    for command in commands:
        print(display(command), flush=True)
        if not args.dry_run:
            subprocess.run(command, cwd=WORK_ROOT, check=True)


if __name__ == "__main__":
    main()
