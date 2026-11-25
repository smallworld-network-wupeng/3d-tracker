#!/usr/bin/env python3
"""Mix a music bed into the final video and duck it under location audio."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def has_audio(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=index", "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return bool(json.loads(result.stdout).get("streams"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--music", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-lufs", type=float, default=-21.0)
    parser.add_argument("--music-volume", type=float, default=1.0)
    parser.add_argument("--start-offset-seconds", type=float, default=0.0)
    parser.add_argument("--duck-threshold", type=float, default=0.025)
    parser.add_argument("--duck-ratio", type=float, default=8.0)
    parser.add_argument("--duck-attack-ms", type=float, default=80.0)
    parser.add_argument("--duck-release-ms", type=float, default=700.0)
    parser.add_argument("--fade-in-seconds", type=float, default=2.0)
    parser.add_argument("--fade-out-seconds", type=float, default=4.0)
    parser.add_argument("--audio-bitrate", default="192k")
    args = parser.parse_args()

    video_duration = duration(args.video)
    start_offset = max(0.0, args.start_offset_seconds)
    music_duration = max(0.001, video_duration - start_offset)
    fade_out_start = max(0.0, music_duration - args.fade_out_seconds)
    delay_ms = round(start_offset * 1000)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    music_bed = (
        f"[1:a:0]atrim=duration={music_duration:.6f},asetpts=PTS-STARTPTS,"
        f"loudnorm=I={args.target_lufs}:LRA=9:TP=-2,volume={args.music_volume},"
        f"afade=t=in:st=0:d={args.fade_in_seconds},"
        f"afade=t=out:st={fade_out_start:.6f}:d={args.fade_out_seconds},"
        f"adelay={delay_ms}:all=1[music]"
    )
    if has_audio(args.video):
        music_filter = (
            music_bed + ";"
            f"[music][0:a:0]sidechaincompress=threshold={args.duck_threshold}:"
            f"ratio={args.duck_ratio}:attack={args.duck_attack_ms}:release={args.duck_release_ms}[ducked];"
            f"[0:a:0][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]"
        )
    else:
        music_filter = music_bed + ";[music]apad,atrim=duration={:.6f},alimiter=limit=0.95[aout]".format(
            video_duration
        )
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "warning", "-i", str(args.video),
        "-stream_loop", "-1", "-i", str(args.music), "-filter_complex", music_filter,
        "-map", "0:v:0", "-map", "[aout]", "-t", f"{video_duration:.6f}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", args.audio_bitrate,
        "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(args.output),
    ], check=True)
    print(f"完成: {args.output}")


if __name__ == "__main__":
    main()
