#!/usr/bin/env python3
"""Insert time-matched GoPro clip groups into a rendered Cesium route video."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def probe(path: Path, require_creation_time: bool = True) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:format_tags=creation_time,com.apple.quicktime.creationdate",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)["format"]
    tags = data.get("tags", {})
    creation = tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time")
    if not creation and require_creation_time:
        raise ValueError(f"缺少 creation_time: {path}")
    local_wall_time = parse_creation_time(creation) if creation else None
    return {"path": path, "created": local_wall_time, "duration": float(data["duration"])}


def parse_creation_time(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"无法识别拍摄时间 {value!r}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    return parsed


def video_geometry(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(result.stdout)["streams"][0]
    width, height = int(stream["width"]), int(stream["height"])
    rotation = int(float(stream.get("tags", {}).get("rotate", 0)))
    for side_data in stream.get("side_data_list", []):
        if "rotation" in side_data:
            rotation = int(float(side_data["rotation"]))
            break
    if abs(rotation) % 180 == 90:
        width, height = height, width
    return width, height


def fit_popup_geometry(
    source_width: int, source_height: int, max_width: int, max_height: int,
) -> tuple[int, int]:
    """Fit a video's natural aspect ratio inside the configured popup bounds."""

    if min(source_width, source_height, max_width, max_height) <= 0:
        raise ValueError("视频与弹窗尺寸必须大于 0")
    scale = min(max_width / source_width, max_height / source_height)
    width = max(2, int(source_width * scale) // 2 * 2)
    height = max(2, int(source_height * scale) // 2 * 2)
    return width, height


def matched_groups(media_dir: Path, activity_start: datetime, activity_end: datetime, window_seconds: int):
    clips = []
    for path in sorted(media_dir.glob("GX*.MP4")):
        item = probe(path)
        if activity_start <= item["created"] <= activity_end:
            clips.append(item)
    groups = []
    for clip in clips:
        if not groups or (clip["created"] - groups[-1][0]["created"]).total_seconds() > window_seconds:
            groups.append([clip])
        else:
            groups[-1].append(clip)
    return groups


def parse_timecode(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"时间码应为 MM:SS 或 HH:MM:SS，而不是 {value!r}")
    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise ValueError(f"无法识别时间码 {value!r}") from exc
    if any(number < 0 for number in numbers) or numbers[-1] >= 60 or (len(numbers) == 3 and numbers[-2] >= 60):
        raise ValueError(f"时间码超出范围: {value!r}")
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]


def load_segment_list(list_path: Path, media_dir: Path) -> tuple[list[dict], list[str], list[str]]:
    segments = []
    errors = []
    warnings = []
    section = ""
    for line_number, raw_line in enumerate(list_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            section = line[1:].strip()
            continue
        parts = [part.strip() for part in line.replace("｜", "|").split("|")]
        if len(parts) not in (1, 3, 4) or not parts[0]:
            errors.append(f"第 {line_number} 行格式错误: {raw_line}")
            continue
        path = media_dir / parts[0]
        if path.name != parts[0] or not path.is_file():
            errors.append(f"第 {line_number} 行找不到视频: {parts[0]}")
            continue
        try:
            creation_override = parts[3] if len(parts) == 4 else ""
            item = probe(path, require_creation_time=not creation_override)
            source_created = (
                parse_creation_time(creation_override) if creation_override else item["created"]
            )
            start = 0.0
            end = item["duration"]
            if len(parts) in (3, 4):
                if not parts[1] or not parts[2]:
                    raise ValueError("开始时间和结束时间必须同时填写")
                start = parse_timecode(parts[1])
                end = parse_timecode(parts[2])
                if end <= start:
                    raise ValueError(f"结束时间 {parts[2]} 必须晚于开始时间 {parts[1]}")
                if start >= item["duration"]:
                    raise ValueError(f"开始时间 {parts[1]} 超过视频长度 {item['duration']:.3f}s")
                if end > item["duration"]:
                    warnings.append(
                        f"第 {line_number} 行 {parts[0]}: 结束时间 {parts[2]} 超过视频长度 "
                        f"{item['duration']:.3f}s，已截到文件末尾"
                    )
                    end = item["duration"]
            segments.append({
                "path": path,
                "source_created": source_created,
                "created": source_created + timedelta(seconds=start),
                "start": start,
                "end": end,
                "duration": end - start,
                "section": section,
                "line": line_number,
            })
        except ValueError as exc:
            errors.append(f"第 {line_number} 行 {parts[0]}: {exc}")
    return segments, errors, warnings


def group_segments(segments: list[dict], window_seconds: int) -> list[list[dict]]:
    groups = []
    for segment in sorted(segments, key=lambda item: (item["created"], item["line"])):
        if not groups or (segment["created"] - groups[-1][0]["created"]).total_seconds() > window_seconds:
            groups.append([segment])
        else:
            groups[-1].append(segment)
    return groups


def local_wall_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    return parsed


def normalize_group(
    group: list[dict], output: Path, per_clip_seconds: Optional[float], fps: int,
    popup_width: int, popup_height: int,
) -> float:
    command = ["ffmpeg", "-y", "-loglevel", "warning"]
    durations = []
    for clip in group:
        duration = clip["duration"] if per_clip_seconds is None else min(per_clip_seconds, clip["duration"])
        durations.append(duration)
        command.extend([
            "-ss", f"{clip.get('start', 0.0):.6f}", "-t", f"{duration:.6f}", "-i", str(clip["path"])
        ])
    filters = []
    concat_inputs = []
    for index, duration in enumerate(durations):
        filters.append(
            f"[{index}:v:0]trim=duration={duration:.6f},setpts=PTS-STARTPTS,"
            f"scale={popup_width}:{popup_height}:force_original_aspect_ratio=increase:force_divisible_by=2,"
            f"crop={popup_width}:{popup_height},"
            f"fps={fps},format=yuv420p[v{index}]"
        )
        filters.append(
            f"[{index}:a:0]atrim=duration={duration:.6f},asetpts=PTS-STARTPTS,"
            f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{index}]"
        )
        concat_inputs.append(f"[v{index}][a{index}]")
    filters.append(
        "".join(concat_inputs) + f"concat=n={len(group)}:v=1:a=1[vout][aout]"
    )
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(output),
    ])
    run(command)
    return sum(durations)


def render_map_segment(base: Path, start: float, end: float, output: Path, fps: int) -> None:
    duration = max(0.001, end - start)
    run([
        "ffmpeg", "-y", "-loglevel", "warning", "-ss", f"{start:.6f}", "-t", f"{duration:.6f}",
        "-i", str(base), "-f", "lavfi", "-t", f"{duration:.6f}",
        "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v:0", "-map", "1:a:0",
        "-vf", f"fps={fps},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "19", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-shortest", str(output),
    ])


def render_popup(
    base: Path, group_video: Path, base_time: float, duration: float, output: Path, fps: int,
    popup_width: int, popup_height: int, popup_border: int, background_brightness: float,
    base_width: int, base_height: int, background_advance: float, popup_y: int,
) -> None:
    card_width = popup_width + popup_border * 2
    card_height = popup_height + popup_border * 2
    if background_advance <= 0:
        # Keep all baked-in live metrics (heart rate, pace, elapsed time, etc.)
        # on the exact frame where the popup starts.  The map timeline resumes
        # from this same frame after the popup finishes.
        background_filter = (
            f"[0:v:0]trim=end_frame=1,setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={duration:.6f},fps={fps},"
        )
    else:
        background_span = max(1.0 / fps, background_advance)
        background_speed_factor = duration / background_span
        background_filter = (
            f"[0:v:0]trim=duration={background_span:.6f},"
            f"setpts={background_speed_factor:.9f}*(PTS-STARTPTS),"
            f"tpad=stop_mode=clone:stop_duration={duration:.6f},"
            f"framerate=fps={fps}:interp_start=0:interp_end=255:scene=100,"
        )
    resolved_y = max(0, min(popup_y, base_height - card_height))
    card_y = "(H-h)/2" if popup_y < 0 else str(resolved_y)
    crop_y = f"(ih-{card_height})/2" if popup_y < 0 else str(resolved_y)
    video_y = "(H-h)/2" if popup_y < 0 else str(resolved_y + popup_border)
    blur_radius = max(4, min(24, popup_border * 2))
    highlight_width = max(1, popup_border // 5)
    run([
        "ffmpeg", "-y", "-loglevel", "warning", "-ss", f"{base_time:.6f}", "-i", str(base),
        "-i", str(group_video), "-filter_complex",
        (
            background_filter
            + f"scale={base_width}:{base_height},eq=brightness={background_brightness:.3f}[bgbase];"
            f"[bgbase]split=2[bg][glassbase];"
            f"[glassbase]crop={card_width}:{card_height}:(iw-{card_width})/2:{crop_y},"
            f"boxblur=lr={blur_radius}:lp=2,eq=brightness=0.035:saturation=0.72,"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.28:t={highlight_width}[glass];"
            f"[1:v:0]setpts=PTS-STARTPTS[video];"
            f"[bg][glass]overlay=(W-w)/2:{card_y}[framed];"
            f"[framed][video]overlay=(W-w)/2:{video_y}:shortest=1,format=yuv420p[vout];"
            f"[1:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[aout]"
        ),
        "-map", "[vout]", "-map", "[aout]", "-t", f"{duration:.6f}",
        "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-shortest", str(output),
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--media-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--activity-start", help="活动本地开始时间；默认读取 track-json")
    parser.add_argument("--activity-end", help="活动本地结束时间；默认读取 track-json")
    parser.add_argument("--track-json", type=Path, default=Path("web/track.json"))
    parser.add_argument("--render-config", type=Path, default=Path("web/render-config.json"))
    parser.add_argument("--base-seconds", type=float, default=60.0)
    parser.add_argument("--group-window", type=int, default=600)
    parser.add_argument("--per-clip-seconds", type=float, default=3.0)
    parser.add_argument("--segment-list", type=Path, help="精选片段 TXT；未写时间码的条目使用整个视频")
    parser.add_argument("--skip-invalid", action="store_true", help="跳过清单中的错误行并继续生成")
    parser.add_argument("--groups", default="", help="1-based group indices, e.g. 1,9,17; empty means all")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--popup-width", type=int, default=720, help="弹窗最大宽度")
    parser.add_argument("--popup-height", type=int, default=540, help="弹窗最大高度")
    parser.add_argument("--popup-border", type=int, default=10)
    parser.add_argument(
        "--popup-y", type=int, default=-1,
        help="弹窗顶部 Y 坐标（像素）；负数表示垂直居中",
    )
    parser.add_argument("--background-brightness", type=float, default=-0.18)
    parser.add_argument(
        "--popup-background-advance", type=float, default=0.0,
        help="弹窗期间消耗到下一事件之间底片时长的比例（0=冻结，1=完全推进）",
    )
    parser.add_argument("--report", type=Path, default=Path("output/media-events.json"))
    args = parser.parse_args()
    args.popup_width = max(2, round(args.popup_width / 2) * 2)
    args.popup_height = max(2, round(args.popup_height / 2) * 2)

    track_metadata = json.loads(args.track_json.read_text(encoding="utf-8"))["metadata"]
    render_config = (
        json.loads(args.render_config.read_text(encoding="utf-8"))
        if args.render_config.is_file() else {}
    )
    activity_start = local_wall_time(args.activity_start or track_metadata["start"])
    activity_end = local_wall_time(args.activity_end or track_metadata["end"])
    base_width, base_height = video_geometry(args.base)
    activity_duration = (activity_end - activity_start).total_seconds()
    validation_errors = []
    validation_warnings = []
    if args.segment_list:
        segments, validation_errors, validation_warnings = load_segment_list(args.segment_list, args.media_dir)
        if validation_errors and not args.skip_invalid:
            raise SystemExit("清单校验失败:\n" + "\n".join(f"- {error}" for error in validation_errors))
        if not segments:
            raise SystemExit("清单中没有可用的视频片段")
        groups = group_segments(segments, args.group_window)
        clip_limit = None
    else:
        groups = matched_groups(args.media_dir, activity_start, activity_end, args.group_window)
        clip_limit = args.per_clip_seconds
    selected_indices = (
        [int(value) for value in args.groups.split(",") if value.strip()]
        if args.groups else list(range(1, len(groups) + 1))
    )
    selected = [(index, groups[index - 1]) for index in selected_indices]

    events = []
    for index, group in selected:
        activity_offset = (group[0]["created"] - activity_start).total_seconds()
        track_progress = max(0.0, min(1.0, activity_offset / activity_duration))
        intro_ratio = float(render_config.get("intro_ratio", 0.07))
        outro_ratio = float(render_config.get("outro_ratio", 0.07))
        track_ratio = max(0.001, 1.0 - intro_ratio - outro_ratio)
        base_time = args.base_seconds * (intro_ratio + track_ratio * track_progress)
        events.append({
            "group": index,
            "created": group[0]["created"].isoformat(),
            "base_time": base_time,
            "files": [str(item["path"]) for item in group],
            "segments": [
                {
                    "file": item["path"].name,
                    "start": item.get("start", 0.0),
                    "end": item.get("end", item["duration"]),
                    "duration": item["duration"],
                    "section": item.get("section", ""),
                    "line": item.get("line"),
                }
                for item in group
            ],
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="route-media-") as temporary:
        temp = Path(temporary)
        timeline_parts = []
        previous_base_time = 0.0
        for event_number, (event, (_group_index, group)) in enumerate(zip(events, selected), 1):
            map_segment = temp / f"{len(timeline_parts):03d}_map.mp4"
            render_map_segment(args.base, previous_base_time, event["base_time"], map_segment, args.fps)
            timeline_parts.append(map_segment)

            normalized = temp / f"group_{event_number:03d}.mp4"
            source_width, source_height = video_geometry(group[0]["path"])
            popup_width, popup_height = fit_popup_geometry(
                source_width, source_height, args.popup_width, args.popup_height
            )
            event["source_geometry"] = [source_width, source_height]
            event["popup_geometry"] = [popup_width, popup_height]
            event["popup_duration"] = normalize_group(
                group, normalized, clip_limit, args.fps, popup_width, popup_height
            )
            popup = temp / f"{len(timeline_parts):03d}_popup.mp4"
            next_base_time = (
                events[event_number]["base_time"]
                if event_number < len(events) else args.base_seconds
            )
            available_advance = max(0.0, next_base_time - event["base_time"])
            event["background_advance"] = available_advance * max(
                0.0, min(1.0, args.popup_background_advance)
            )
            render_popup(
                args.base, normalized, event["base_time"], event["popup_duration"], popup,
                args.fps, popup_width, popup_height, args.popup_border,
                args.background_brightness, base_width, base_height, event["background_advance"],
                args.popup_y,
            )
            timeline_parts.append(popup)
            previous_base_time = event["base_time"] + event["background_advance"]
            print(
                f"事件 {event_number}/{len(events)}: 组 {event['group']} · "
                f"{len(group)} 段 · {event['popup_duration']:.1f}s · 地图 {event['base_time']:.2f}s",
                flush=True,
            )

        final_map = temp / f"{len(timeline_parts):03d}_map.mp4"
        render_map_segment(args.base, previous_base_time, args.base_seconds, final_map, args.fps)
        timeline_parts.append(final_map)
        concat_file = temp / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{part.as_posix()}'\n" for part in timeline_parts), encoding="utf-8"
        )
        expected_duration = args.base_seconds + sum(
            event["popup_duration"] - event["background_advance"] for event in events
        )
        run([
            "ffmpeg", "-y", "-loglevel", "warning", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-vf", (
                f"tpad=stop_mode=clone:stop_duration=1,fps={args.fps},"
                f"trim=duration={expected_duration:.6f},setpts=PTS-STARTPTS,format=yuv420p"
            ),
            "-af", (
                f"aresample=async=1:first_pts=0,apad=pad_dur=1,"
                f"atrim=duration={expected_duration:.6f},asetpts=PTS-STARTPTS"
            ),
            "-t", f"{expected_duration:.6f}", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "19", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(args.output),
        ])

    report = {
        "activity_start": activity_start.isoformat(),
        "activity_end": activity_end.isoformat(),
        "group_window_seconds": args.group_window,
        "segment_list": str(args.segment_list) if args.segment_list else None,
        "validation_errors": validation_errors,
        "validation_warnings": validation_warnings,
        "matched_clip_count": sum(len(group) for group in groups),
        "all_group_count": len(groups),
        "selected_group_count": len(events),
        "events": events,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成: {args.output}")


if __name__ == "__main__":
    main()
