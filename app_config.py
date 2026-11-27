#!/usr/bin/env python3
"""Shared project model for the 3D track movie desktop application."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SUPPORTED_TRACK_SUFFIXES = {".fit", ".kml"}
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}
SUPPORTED_MUSIC_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac"}
INTRO_RATIO = 0.07
OUTRO_RATIO = 0.20
VIDEO_GROUP_WINDOW = 600
DEFAULT_FPS = 30
SEGMENT_CONFIG_FILENAME = "video_segments.json"
SEGMENT_CONFIG_SCHEMA_VERSION = 1
PROJECT_FILE_SUFFIX = ".3dtrack"
PROJECT_FILE_SCHEMA_VERSION = 1


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
        if not math.isfinite(self.start) or not math.isfinite(self.end):
            raise ValueError("片段时间必须是有限数字")
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

    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON 格式错误（第 {exc.lineno} 行，第 {exc.colno} 列）"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError("片段配置的最外层必须是 JSON 对象")
    if document.get("schema_version") != SEGMENT_CONFIG_SCHEMA_VERSION:
        raise ValueError(
            f"不支持的片段配置版本: {document.get('schema_version')!r}"
        )
    videos = document.get("videos")
    if not isinstance(videos, list):
        raise ValueError("片段配置中的 videos 必须是数组")

    segments: list[Segment] = []
    filenames: set[str] = set()
    for video_index, video in enumerate(videos, 1):
        location = f"第 {video_index} 个视频"
        if not isinstance(video, dict):
            raise ValueError(f"{location}必须是 JSON 对象")
        filename = video.get("file")
        if not isinstance(filename, str):
            raise ValueError(f"{location}的 file 必须是字符串")
        if not filename or Path(filename).name != filename:
            raise ValueError(f"{location}的影片文件名无效")
        if filename in filenames:
            raise ValueError(f"{location}重复定义了影片 {filename}")
        filenames.add(filename)
        raw_creation_time = video.get("creation_time")
        if raw_creation_time is not None and not isinstance(raw_creation_time, str):
            raise ValueError(f"{location}的 creation_time 必须是字符串或 null")
        try:
            creation_time = (
                normalize_creation_time(raw_creation_time) if raw_creation_time else None
            )
        except ValueError as exc:
            raise ValueError(f"{location}的 creation_time: {exc}") from exc
        intervals = video.get("segments")
        if not isinstance(intervals, list):
            raise ValueError(f"{location}的 segments 必须是数组")
        if not intervals:
            raise ValueError(f"{location}的 segments 不能为空")
        for segment_index, interval in enumerate(intervals, 1):
            interval_location = f"{location}的第 {segment_index} 个片段"
            if not isinstance(interval, dict):
                raise ValueError(f"{interval_location}必须是 JSON 对象")
            start = interval.get("start_seconds")
            end = interval.get("end_seconds")
            if not _is_json_number(start) or not _is_json_number(end):
                raise ValueError(
                    f"{interval_location}的 start_seconds 和 end_seconds 必须是数字"
                )
            segment = Segment(filename, float(start), float(end), creation_time)
            try:
                segment.validate()
            except ValueError as exc:
                raise ValueError(f"{interval_location}: {exc}") from exc
            segments.append(segment)
    return segments


def _is_json_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def write_segment_list(path: Path, segments: list[Segment]) -> None:
    for segment in segments:
        segment.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    videos: list[dict] = []
    grouped: dict[str, list[Segment]] = {}
    for segment in sorted(segments, key=lambda item: (item.file.casefold(), item.start, item.end)):
        grouped.setdefault(segment.file, []).append(segment)
    for filename, file_segments in grouped.items():
        creation_times = {
            normalize_creation_time(segment.creation_time)
            for segment in file_segments
            if segment.creation_time
        }
        if len(creation_times) > 1:
            raise ValueError(f"{filename} 的多个片段使用了不同的拍摄时间")
        video = {
            "file": filename,
            "segments": [
                {
                    "start_seconds": segment.start,
                    "end_seconds": segment.end,
                }
                for segment in file_segments
            ],
        }
        if creation_times:
            video["creation_time"] = next(iter(creation_times))
        videos.append(video)
    document = {
        "schema_version": SEGMENT_CONFIG_SCHEMA_VERSION,
        "videos": videos,
    }
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def list_video_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (
            path for path in directory.iterdir()
            if (
                path.is_file()
                and not path.name.startswith(".")
                and path.suffix.lower() in SUPPORTED_VIDEO_SUFFIXES
            )
        ),
        key=lambda path: path.name.casefold(),
    )


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "轨迹影片"


def _project_path_value(value: Path | None, project_directory: Path) -> str:
    """Store project-local paths relatively so a project directory can be moved."""

    if value is None:
        return ""
    resolved = value.expanduser().resolve()
    try:
        return resolved.relative_to(project_directory.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_project_path(value: object, project_directory: Path, location: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"项目文件中的 {location} 必须是字符串")
    if not value:
        return ""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_directory / path
    return str(path.resolve())


def build_editor_project(
    *,
    project_path: Path,
    track_file: Path | None,
    activity_name: str,
    orientation: str,
    quality: str,
    seconds: float,
    output_directory: Path | None,
    media_directory: Path | None,
    segments: list[Segment],
    photo_directory: Path | None,
    photo_events: list[dict],
    music_file: Path | None,
    music_start_offset_seconds: float,
) -> dict:
    """Build the single, user-facing project document used by the editor."""

    if orientation not in {"landscape", "portrait"}:
        raise ValueError("不支持的画面方向")
    if quality not in {"720p", "1080p"}:
        raise ValueError("不支持的输出画质")
    if seconds <= 0:
        raise ValueError("影片时长必须大于 0")
    if music_start_offset_seconds < 0:
        raise ValueError("背景音乐开始偏移不能小于 0")
    for segment in segments:
        segment.validate()

    root = project_path.expanduser().resolve().parent
    return {
        "schema_version": PROJECT_FILE_SCHEMA_VERSION,
        "kind": "3d-track-project",
        "track": {
            "file": _project_path_value(track_file, root),
            "name": activity_name.strip(),
        },
        "movie": {
            "orientation": orientation,
            "quality": quality,
            "seconds": float(seconds),
        },
        "video": {
            "directory": _project_path_value(media_directory, root),
            "segments": [
                {
                    "file": segment.file,
                    "start_seconds": segment.start,
                    "end_seconds": segment.end,
                    "creation_time": segment.creation_time,
                }
                for segment in segments
            ],
        },
        "photos": {
            "directory": _project_path_value(photo_directory, root),
            "events": photo_events,
        },
        "music": {
            "file": _project_path_value(music_file, root),
            "start_offset_seconds": float(music_start_offset_seconds),
        },
        "output": {
            "directory": _project_path_value(output_directory, root),
        },
    }


def read_editor_project(path: Path) -> dict:
    """Read and strictly validate the current project-file format."""

    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"项目文件 JSON 格式错误（第 {exc.lineno} 行，第 {exc.colno} 列）"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError("项目文件的最外层必须是 JSON 对象")
    if document.get("kind") != "3d-track-project":
        raise ValueError("这不是 3D 轨迹影片项目文件")
    if document.get("schema_version") != PROJECT_FILE_SCHEMA_VERSION:
        raise ValueError(f"不支持的项目文件版本: {document.get('schema_version')!r}")

    for key in ("track", "movie", "video", "photos", "music", "output"):
        if not isinstance(document.get(key), dict):
            raise ValueError(f"项目文件中的 {key} 必须是 JSON 对象")
    movie = document["movie"]
    if not isinstance(document["track"].get("name", ""), str):
        raise ValueError("项目文件中的活动名称必须是字符串")
    if movie.get("orientation") not in {"landscape", "portrait"}:
        raise ValueError("项目文件中的画面方向无效")
    if movie.get("quality") not in {"720p", "1080p"}:
        raise ValueError("项目文件中的输出画质无效")
    seconds = movie.get("seconds")
    if not _is_json_number(seconds) or seconds <= 0:
        raise ValueError("项目文件中的影片时长无效")
    music_offset = document["music"].get("start_offset_seconds", 0.0)
    if not _is_json_number(music_offset) or music_offset < 0:
        raise ValueError("项目文件中的背景音乐开始偏移无效")

    raw_segments = document["video"].get("segments")
    raw_events = document["photos"].get("events")
    if not isinstance(raw_segments, list):
        raise ValueError("项目文件中的 video.segments 必须是数组")
    if not isinstance(raw_events, list):
        raise ValueError("项目文件中的 photos.events 必须是数组")
    segments = []
    for index, item in enumerate(raw_segments, 1):
        if not isinstance(item, dict):
            raise ValueError(f"项目文件中的第 {index} 个视频片段必须是 JSON 对象")
        try:
            segment = Segment(
                file=item["file"],
                start=float(item["start_seconds"]),
                end=float(item["end_seconds"]),
                creation_time=item.get("creation_time"),
            )
            segment.validate()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"项目文件中的第 {index} 个视频片段无效: {exc}") from exc
        segments.append(segment)

    root = path.expanduser().resolve().parent
    track = document["track"]
    music = document["music"]
    output = document["output"]
    video = document["video"]
    photos = document["photos"]
    result = dict(document)
    result["track"] = dict(track, file=_resolve_project_path(track.get("file", ""), root, "track.file"))
    result["video"] = dict(
        video,
        directory=_resolve_project_path(video.get("directory", ""), root, "video.directory"),
        segments=segments,
    )
    result["photos"] = dict(
        photos,
        directory=_resolve_project_path(photos.get("directory", ""), root, "photos.directory"),
    )
    result["music"] = dict(
        music,
        file=_resolve_project_path(music.get("file", ""), root, "music.file"),
    )
    result["output"] = dict(
        output,
        directory=_resolve_project_path(output.get("directory", ""), root, "output.directory"),
    )
    return result


def write_editor_project(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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
    segments: list[Segment] | None = None,
    photo_directory: Path | None = None,
    photo_events: list[dict] | None = None,
    music_file: Path | None = None,
    music_start_offset_seconds: float = 0.0,
    preview: bool = False,
) -> tuple[dict, Path]:
    """Build the existing pipeline's JSON while keeping expert values internal."""

    if not track_file.is_file() or track_file.suffix.lower() not in SUPPORTED_TRACK_SUFFIXES:
        raise ValueError("请选择有效的 FIT 或 KML 轨迹文件")
    if not activity_name.strip():
        raise ValueError("请填写活动名称")
    if seconds <= 0:
        raise ValueError("影片时长必须大于 0")
    if music_start_offset_seconds < 0:
        raise ValueError("背景音乐开始偏移不能小于 0")

    output_directory = output_directory.resolve()
    work_directory = output_directory / ".3d_track_work"
    stem = safe_filename(activity_name)
    width, height = output_dimensions(orientation, quality)

    selected_segments = segments or []
    selected_photos = photo_events or []
    clips_enabled = bool(
        not preview
        and media_directory
        and media_directory.is_dir()
        and selected_segments
    )
    photos_enabled = bool(
        not preview
        and photo_directory
        and any(event.get("enabled", False) for event in selected_photos)
    )
    media_enabled = clips_enabled or photos_enabled
    music_enabled = bool(not preview and music_file and music_file.is_file())
    has_postprocessing = media_enabled or music_enabled

    final_output = output_directory / f"{stem}.mp4"
    map_output = work_directory / ("preview.mp4" if preview else f"{stem}-map.mp4")
    if not has_postprocessing and not preview:
        map_output = final_output
    media_output = final_output if media_enabled and not music_enabled else work_directory / f"{stem}-clips.mp4"

    is_portrait = orientation == "portrait"
    render_seconds = min(8.0, seconds) if preview else float(seconds)
    render_fps = 15 if preview else DEFAULT_FPS
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
        "intro_ratio": INTRO_RATIO,
        "outro_ratio": OUTRO_RATIO,
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
            "directory": str(media_directory.resolve()) if clips_enabled else "",
            "segments": [
                {
                    "file": segment.file,
                    "start_seconds": segment.start,
                    "end_seconds": segment.end,
                    "creation_time": segment.creation_time,
                }
                for segment in selected_segments
            ] if clips_enabled else [],
            "photo_directory": str(photo_directory.resolve()) if photos_enabled else "",
            "photos": selected_photos if photos_enabled else [],
            "output": str(media_output),
            "report": str(work_directory / f"{stem}-media-events.json"),
            "group_window_seconds": VIDEO_GROUP_WINDOW,
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
            "start_offset_seconds": float(music_start_offset_seconds),
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
