#!/usr/bin/env python3
"""Shared project model for the 3D track movie desktop application."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SUPPORTED_TRACK_SUFFIXES = {".fit", ".kml"}
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}
SUPPORTED_MUSIC_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac"}


@dataclass(frozen=True)
class Segment:
    """One selected interval from a source video."""

    file: str
    start: float
    end: float
    creation_time: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start

    def validate(self) -> None:
        if not self.file or Path(self.file).name != self.file:
            raise ValueError("影片文件名无效")
        if self.start < 0:
            raise ValueError("起点不能小于 0")
        if self.end <= self.start:
            raise ValueError("终点必须晚于起点")
        if self.creation_time:
            normalize_creation_time(self.creation_time)


def parse_creation_time(value: str) -> datetime:
    """Parse a video's creation time as an Asia/Shanghai local wall-clock value."""

    raw = value.strip()
    if not raw:
        raise ValueError("请填写拍摄时间")
    # Keep compatibility with GoPro files in this project: their trailing Z is
    # known to label an already-local wall-clock value rather than UTC.
    if raw.endswith("Z"):
        raw = raw[:-1]
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("拍摄时间应写成 YYYY-MM-DD HH:MM:SS") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    return parsed


def normalize_creation_time(value: str) -> str:
    """Return the canonical segment-list representation of a creation time."""

    return parse_creation_time(value).isoformat(timespec="seconds")


def display_creation_time(value: str) -> str:
    """Return a creation time formatted for the desktop editor."""

    return parse_creation_time(value).strftime("%Y-%m-%d %H:%M:%S")


def format_timecode(seconds: float) -> str:
    """Format seconds as a segment-list-compatible HH:MM:SS.mmm value."""

    total_milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def parse_timecode(value: str) -> float:
    """Parse MM:SS or HH:MM:SS, optionally with fractional seconds."""

    parts = value.strip().split(":")
    if len(parts) not in (2, 3):
        raise ValueError("时间应写成 MM:SS 或 HH:MM:SS")
    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise ValueError("无法识别这个时间") from exc
    if any(number < 0 for number in numbers):
        raise ValueError("时间不能小于 0")
    if numbers[-1] >= 60 or (len(numbers) == 3 and numbers[-2] >= 60):
        raise ValueError("秒和分钟不能大于等于 60")
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]


def read_segment_list(path: Path) -> list[Segment]:
    if not path.is_file():
        return []
    segments: list[Segment] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.replace("｜", "|").split("|")]
        if len(parts) not in (3, 4):
            raise ValueError(f"第 {line_number} 行格式错误")
        creation_time = normalize_creation_time(parts[3]) if len(parts) == 4 and parts[3] else None
        segment = Segment(
            parts[0], parse_timecode(parts[1]), parse_timecode(parts[2]), creation_time
        )
        segment.validate()
        segments.append(segment)
    return segments


def write_segment_list(path: Path, segments: list[Segment]) -> None:
    for segment in segments:
        segment.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 由 3D轨迹影片生成器 保存", ""]
    current_file = None
    for segment in sorted(segments, key=lambda item: (item.file.casefold(), item.start, item.end)):
        if current_file is not None and segment.file != current_file:
            lines.append("")
        line = f"{segment.file} | {format_timecode(segment.start)} | {format_timecode(segment.end)}"
        if segment.creation_time:
            line += f" | {normalize_creation_time(segment.creation_time)}"
        lines.append(line)
        current_file = segment.file
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def list_video_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (
            path for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_SUFFIXES
        ),
        key=lambda path: path.name.casefold(),
    )


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "轨迹影片"


def output_dimensions(orientation: str, quality: str) -> tuple[int, int]:
    values = {
        ("landscape", "720p"): (1280, 720),
        ("landscape", "1080p"): (1920, 1080),
        ("portrait", "720p"): (720, 1280),
        ("portrait", "1080p"): (1080, 1920),
    }
    try:
        return values[(orientation, quality)]
    except KeyError as exc:
        raise ValueError("不支持的画面方向或输出画质") from exc


def popup_safe_bounds(canvas_width: int, canvas_height: int) -> tuple[int, int]:
    """Return the largest media area that stays clear of the canvas overlays."""

    if min(canvas_width, canvas_height) <= 0:
        raise ValueError("画布尺寸必须大于 0")
    if canvas_height > canvas_width:
        # Portrait output has its information cards above the media and metrics
        # below it.  Use most of the width and the full safe vertical corridor.
        width_ratio, height_ratio = 0.90, 0.575
    else:
        # Landscape output has less vertical room; these ratios preserve the
        # established 720 x 480 media area on a 1280 x 720 canvas.
        width_ratio, height_ratio = 0.5625, 2.0 / 3.0

    def even(value: float) -> int:
        return max(2, round(value / 2) * 2)

    return even(canvas_width * width_ratio), even(canvas_height * height_ratio)


def build_project_config(
    *,
    track_file: Path,
    activity_name: str,
    orientation: str,
    quality: str,
    seconds: float,
    output_directory: Path,
    media_directory: Path | None = None,
    segment_list: Path | None = None,
    segments: list[Segment] | None = None,
    music_file: Path | None = None,
    preview: bool = False,
) -> tuple[dict, Path]:
    """Build the existing pipeline's JSON while keeping expert values internal."""

    if not track_file.is_file() or track_file.suffix.lower() not in SUPPORTED_TRACK_SUFFIXES:
        raise ValueError("请选择有效的 FIT 或 KML 轨迹文件")
    if not activity_name.strip():
        raise ValueError("请填写活动名称")
    if seconds <= 0:
        raise ValueError("影片时长必须大于 0")

    output_directory = output_directory.resolve()
    work_directory = output_directory / ".3d_track_work"
    stem = safe_filename(activity_name)
    width, height = output_dimensions(orientation, quality)

    selected_segments = segments or []
    media_enabled = bool(
        not preview
        and media_directory
        and media_directory.is_dir()
        and segment_list
        and selected_segments
    )
    music_enabled = bool(not preview and music_file and music_file.is_file())
    has_postprocessing = media_enabled or music_enabled

    final_output = output_directory / f"{stem}.mp4"
    map_output = work_directory / ("preview.mp4" if preview else f"{stem}-map.mp4")
    if not has_postprocessing and not preview:
        map_output = final_output
    media_output = final_output if media_enabled and not music_enabled else work_directory / f"{stem}-clips.mp4"

    is_portrait = orientation == "portrait"
    render_seconds = min(8.0, seconds) if preview else float(seconds)
    render_fps = 15 if preview else 30
    if preview:
        width, height = ((960, 540) if not is_portrait else (540, 960))

    popup_width, popup_height = popup_safe_bounds(width, height)

    render = {
        "output": str(map_output),
        "seconds": render_seconds,
        "fps": render_fps,
        "width": width,
        "height": height,
        "terrain_max_level": 14,
        "terrain_exaggeration": 1.35,
        "imagery_max_level": 14,
        "imagery_margin_deg": 0.15,
        "intro_ratio": 0.07,
        "outro_ratio": 0.20,
        "camera_pitch_deg": -57.0,
        "camera_range_m": 11500.0 if is_portrait else 9500.0,
        "auto_camera_range": True,
        "camera_min_range_m": 3000.0 if is_portrait else 2200.0,
        "camera_max_range_m": 120000.0,
        "camera_fit_horizontal": 0.78 if is_portrait else 0.74,
        "camera_fit_vertical": 0.62 if is_portrait else 0.74,
        "camera_fit_padding": 1.10,
        "camera_screen_y": 0.08 if is_portrait else 0.14,
        "camera_look_ahead_m": 500.0,
        "camera_target_lead": 0.65,
        "orbit_start_deg": 18.0,
        "orbit_degrees": 70.0,
        "overview_heading_deg": 18.0,
        "overview_pitch_deg": -50.0 if is_portrait else -45.0,
        "overview_min_range_m": 26000.0 if is_portrait else 18000.0,
        "overview_range_scale": 1.25 if is_portrait else 1.0,
        "overview_start_scale": 1.16,
        "overview_end_scale": 1.0,
        "overview_distance_scale": 1.12,
        "final_orbit_degrees": 180.0,
        "final_pitch_deg": -74.0 if is_portrait else -72.0,
        "final_range_scale": 1.25 if is_portrait else 1.18,
        "metric_scale": 1.5 if is_portrait else 1.0,
        "portrait_profile_width": 520.0,
        "landscape_title_width": 460.0,
        "jpeg_quality": 94,
        "crf": 18,
        "preset": "veryfast",
    }

    config = {
        "schema_version": 1,
        "project": {
            "orientation": orientation,
            "quality": quality,
            "preview": preview,
        },
        "track": {
            "file": str(track_file.resolve()),
            "name": activity_name.strip(),
            "sample_seconds": 5.0,
            "simplify_meters": 2.0,
        },
        "render": render,
        "media": {
            "enabled": media_enabled,
            "directory": str(media_directory.resolve()) if media_directory else "",
            "segment_list": str(segment_list.resolve()) if segment_list else "",
            "output": str(media_output),
            "report": str(work_directory / f"{stem}-media-events.json"),
            "group_window_seconds": 600,
            "popup_width": popup_width,
            "popup_height": popup_height,
            "popup_border": 12 if is_portrait else 10,
            "popup_y": -1 if is_portrait else round(height * 205 / 720),
            "background_brightness": -0.18,
            "popup_background_advance": 0.0,
        },
        "music": {
            "enabled": music_enabled,
            "file": str(music_file.resolve()) if music_file else "",
            "output": str(final_output),
            "target_lufs": -18.0,
            "music_volume": 1.0,
            "start_offset_seconds": 0.0,
            "duck_threshold": 0.04,
            "duck_ratio": 4.0,
            "duck_attack_ms": 80.0,
            "duck_release_ms": 700.0,
            "fade_in_seconds": 2.0,
            "fade_out_seconds": 4.0,
            "audio_bitrate": "192k",
        },
    }
    return config, map_output if preview else final_output


def write_project_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
