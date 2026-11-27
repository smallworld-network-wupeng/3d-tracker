#!/usr/bin/env python3
"""Turn FIT or Garmin-style timestamped KML tracks into compact Cesium JSON."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(element: ET.Element, name: str) -> Optional[str]:
    for child in element.iter():
        if local_name(child.tag) == name and child.text:
            return child.text.strip()
    return None


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def haversine_m(a: list[float], b: list[float]) -> float:
    radius = 6_371_008.8
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(h)))


def simplify_indices(points: list[list[float]], tolerance_m: float) -> list[int]:
    """Ramer-Douglas-Peucker in a local metric projection, preserving endpoints."""
    if tolerance_m <= 0 or len(points) <= 2:
        return list(range(len(points)))
    radius = 6_371_008.8
    mean_lat = math.radians(sum(point[1] for point in points) / len(points))
    xy = [
        (math.radians(point[0]) * radius * math.cos(mean_lat), math.radians(point[1]) * radius)
        for point in points
    ]
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        ax, ay = xy[start]
        bx, by = xy[end]
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        farthest, farthest_distance = None, -1.0
        for index in range(start + 1, end):
            px, py = xy[index]
            if length_sq == 0:
                distance = math.hypot(px - ax, py - ay)
            else:
                fraction = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
                distance = math.hypot(px - (ax + fraction * dx), py - (ay + fraction * dy))
            if distance > farthest_distance:
                farthest, farthest_distance = index, distance
        if farthest is not None and farthest_distance > tolerance_m:
            keep.add(farthest)
            stack.append((start, farthest))
            stack.append((farthest, end))
    return sorted(keep)


def activity_name(kml_path: Path) -> str:
    # The first Folder/name is the human-readable activity title.
    for _event, element in ET.iterparse(kml_path, events=("end",)):
        if local_name(element.tag) == "name" and element.text:
            return element.text.strip()
    return kml_path.stem


def iter_timed_points(kml_path: Path):
    for _event, element in ET.iterparse(kml_path, events=("end",)):
        if local_name(element.tag) != "Placemark":
            continue
        begin = child_text(element, "begin")
        coordinates = child_text(element, "coordinates")
        has_point = any(local_name(child.tag) == "Point" for child in element.iter())
        if begin and coordinates and has_point:
            parts = [part.strip() for part in coordinates.split(",")]
            if len(parts) >= 2:
                try:
                    lon, lat = float(parts[0]), float(parts[1])
                    altitude = float(parts[2]) if len(parts) > 2 and parts[2] else 0.0
                    yield parse_time(begin), lon, lat, altitude
                except ValueError:
                    pass
        element.clear()


def extract_summary(kml_path: Path) -> dict:
    # Garmin puts these values in the activity description; they are useful labels,
    # while computed geometry below remains the source of truth for animation.
    head = kml_path.read_text(encoding="utf-8", errors="replace")[:120_000]
    values = {}
    patterns = {
        "reported_distance_km": r"Distance:&lt;/td&gt;&lt;td&gt;\s*([0-9.]+)\s*Kilometers",
        "reported_duration": r"Time\s*:&lt;/td&gt;&lt;td&gt;\s*([0-9:]+)",
        "reported_gain_m": r"Elevation Gain\s*:&lt;/td&gt;&lt;td&gt;\s*([0-9.]+)\s*Meters",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, head)
        if match:
            value = match.group(1)
            values[key] = float(value) if key != "reported_duration" else value
    return values


def prepare_kml(
    kml_path: Path,
    output_path: Path | None,
    sample_seconds: float = 5.0,
    simplify_meters: float = 2.0,
    name_override: Optional[str] = None,
) -> dict:
    raw = list(iter_timed_points(kml_path))
    if len(raw) < 2:
        raise ValueError("KML 中没有找到至少两个带 TimeSpan 的 Point 轨迹点")
    raw.sort(key=lambda item: item[0])
    start = raw[0][0]

    sampled = [raw[0]]
    last_time = raw[0][0]
    for point in raw[1:-1]:
        if (point[0] - last_time).total_seconds() >= sample_seconds:
            sampled.append(point)
            last_time = point[0]
    sampled.append(raw[-1])

    sampled_points = []
    cumulative = 0.0
    previous = None
    for timestamp, lon, lat, altitude in sampled:
        current = [lon, lat, altitude]
        if previous is not None:
            cumulative += haversine_m(previous, current)
        elapsed = (timestamp - start).total_seconds()
        sampled_points.append([round(lon, 7), round(lat, 7), round(altitude, 1), round(elapsed, 3), round(cumulative, 1)])
        previous = current

    retained = simplify_indices(sampled_points, simplify_meters)
    points = [sampled_points[index] for index in retained]

    lons = [point[1] for point in raw]
    lats = [point[2] for point in raw]
    alts = [point[3] for point in raw]
    metadata = {
        "name": name_override or activity_name(kml_path),
        "source": kml_path.name,
        "start": raw[0][0].isoformat(),
        "end": raw[-1][0].isoformat(),
        "duration_seconds": round((raw[-1][0] - start).total_seconds(), 3),
        "distance_m": round(cumulative, 1),
        "min_altitude_m": round(min(alts), 1),
        "max_altitude_m": round(max(alts), 1),
        "raw_point_count": len(raw),
        "point_count": len(points),
        "sampled_point_count": len(sampled_points),
        "sample_seconds": sample_seconds,
        "simplify_meters": simplify_meters,
        "center": [round((min(lons) + max(lons)) / 2, 7), round((min(lats) + max(lats)) / 2, 7)],
        "bounds": [round(min(lons), 7), round(min(lats), 7), round(max(lons), 7), round(max(lats), 7)],
        **extract_summary(kml_path),
    }
    payload = {"metadata": metadata, "points": points}
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return metadata


def format_duration(seconds: float) -> str:
    value = max(0, round(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def fit_values(message) -> dict:
    return {field.name: field.value for field in message.fields}


def prepare_fit(
    fit_path: Path,
    output_path: Path | None,
    sample_seconds: float = 5.0,
    simplify_meters: float = 2.0,
    name_override: Optional[str] = None,
) -> dict:
    try:
        import fitdecode
    except ImportError as exc:
        raise RuntimeError("解析 FIT 需要 fitdecode，请先运行: python3 -m pip install fitdecode") from exc

    raw = []
    session = {}
    with fitdecode.FitReader(fit_path, check_crc=fitdecode.CrcCheck.WARN) as reader:
        for frame in reader:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            values = fit_values(frame)
            if frame.name == "session":
                session = values
                continue
            if frame.name != "record":
                continue
            timestamp = values.get("timestamp")
            latitude = values.get("position_lat")
            longitude = values.get("position_long")
            altitude = values.get("enhanced_altitude", values.get("altitude"))
            if timestamp is None or latitude is None or longitude is None or altitude is None:
                continue
            raw.append({
                "timestamp": timestamp,
                "lon": float(longitude) * 180.0 / 2**31,
                "lat": float(latitude) * 180.0 / 2**31,
                "altitude": float(altitude),
                "distance": values.get("distance"),
                "heart_rate": values.get("heart_rate"),
                "speed": values.get("enhanced_speed", values.get("speed")),
            })
    if len(raw) < 2:
        raise ValueError("FIT 中没有找到至少两个带 GPS、时间和海拔的 record")
    raw.sort(key=lambda item: item["timestamp"])
    start = raw[0]["timestamp"]

    sampled = [raw[0]]
    last_time = start
    for record in raw[1:-1]:
        if (record["timestamp"] - last_time).total_seconds() >= sample_seconds:
            sampled.append(record)
            last_time = record["timestamp"]
    sampled.append(raw[-1])

    sampled_points = []
    metrics = []
    cumulative = 0.0
    previous = None
    last_device_distance = None
    for record in sampled:
        current = [record["lon"], record["lat"], record["altitude"]]
        device_distance = record["distance"]
        if device_distance is not None and (last_device_distance is None or float(device_distance) >= last_device_distance):
            cumulative = float(device_distance)
            last_device_distance = cumulative
        elif previous is not None:
            cumulative += haversine_m(previous, current)
        elapsed = (record["timestamp"] - start).total_seconds()
        sampled_points.append([
            round(record["lon"], 7),
            round(record["lat"], 7),
            round(record["altitude"], 1),
            round(elapsed, 3),
            round(cumulative, 1),
        ])
        metrics.append([
            round(elapsed, 3),
            int(record["heart_rate"]) if record["heart_rate"] is not None else None,
            round(float(record["speed"]), 3) if record["speed"] is not None else None,
        ])
        previous = current

    retained = simplify_indices(sampled_points, simplify_meters)
    points = [sampled_points[index] for index in retained]
    lons = [record["lon"] for record in raw]
    lats = [record["lat"] for record in raw]
    alts = [record["altitude"] for record in raw]
    local_zone = ZoneInfo("Asia/Shanghai")
    start_local = raw[0]["timestamp"].astimezone(local_zone)
    end_local = raw[-1]["timestamp"].astimezone(local_zone)
    session_distance = session.get("total_distance")
    session_duration = session.get("total_timer_time")
    if session_duration is None:
        session_duration = session.get("total_elapsed_time")
    reported_duration_seconds = (
        float(session_duration) if session_duration is not None else (raw[-1]["timestamp"] - start).total_seconds()
    )
    metadata = {
        "name": name_override or session.get("sport_profile_name") or fit_path.stem,
        "source": fit_path.name,
        "start": start_local.isoformat(),
        "end": end_local.isoformat(),
        "duration_seconds": round((raw[-1]["timestamp"] - start).total_seconds(), 3),
        "distance_m": round(float(session_distance) if session_distance is not None else cumulative, 1),
        "min_altitude_m": round(min(alts), 1),
        "max_altitude_m": round(max(alts), 1),
        "raw_point_count": len(raw),
        "point_count": len(points),
        "sampled_point_count": len(sampled_points),
        "metric_point_count": len(metrics),
        "sample_seconds": sample_seconds,
        "simplify_meters": simplify_meters,
        "center": [round((min(lons) + max(lons)) / 2, 7), round((min(lats) + max(lats)) / 2, 7)],
        "bounds": [round(min(lons), 7), round(min(lats), 7), round(max(lons), 7), round(max(lats), 7)],
        "reported_distance_km": round(float(session_distance) / 1000, 3) if session_distance is not None else round(cumulative / 1000, 3),
        "reported_duration": format_duration(reported_duration_seconds),
        "reported_duration_seconds": reported_duration_seconds,
        "reported_gain_m": float(session["total_ascent"]) if session.get("total_ascent") is not None else None,
        "avg_heart_rate": session.get("avg_heart_rate"),
        "max_heart_rate": session.get("max_heart_rate"),
    }
    payload = {"metadata": metadata, "points": points, "metrics": metrics}
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return metadata


def prepare(
    source_path: Path,
    output_path: Path | None,
    sample_seconds: float = 5.0,
    simplify_meters: float = 2.0,
    name_override: Optional[str] = None,
) -> dict:
    if source_path.suffix.lower() == ".fit":
        return prepare_fit(source_path, output_path, sample_seconds, simplify_meters, name_override)
    if source_path.suffix.lower() == ".kml":
        return prepare_kml(source_path, output_path, sample_seconds, simplify_meters, name_override)
    raise ValueError(f"不支持的轨迹格式: {source_path.suffix}；请使用 .fit 或 .kml")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("track", type=Path, help="FIT 或 KML 轨迹文件")
    parser.add_argument("-o", "--output", type=Path, default=Path("web/track.json"))
    parser.add_argument("--sample-seconds", type=float, default=5.0)
    parser.add_argument("--simplify-meters", type=float, default=2.0)
    parser.add_argument("--name", help="覆盖活动名称")
    args = parser.parse_args()
    metadata = prepare(args.track, args.output, args.sample_seconds, args.simplify_meters, args.name)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
