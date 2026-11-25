#!/usr/bin/env python3
"""Cache Esri World Imagery tiles around a WGS84 bounding box."""

from __future__ import annotations

import argparse
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from prepare_terrain import lon_lat_to_tile


ESRI_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def imagery_tiles(bounds: list[float], min_level: int = 8, max_level: int = 14, padding: int = 3):
    west, south, east, north = bounds
    result = []
    for level in range(min_level, max_level + 1):
        southwest = lon_lat_to_tile(west, south, level)
        northeast = lon_lat_to_tile(east, north, level)
        count = 2**level
        min_x = max(0, min(southwest[0], northeast[0]) - padding)
        max_x = min(count - 1, max(southwest[0], northeast[0]) + padding)
        min_y = max(0, min(southwest[1], northeast[1]) - padding)
        max_y = min(count - 1, max(southwest[1], northeast[1]) + padding)
        result.extend((level, x, y) for x in range(min_x, max_x + 1) for y in range(min_y, max_y + 1))
    return result


def download_tile(tile, output_dir: Path, retries: int = 5) -> bool:
    level, x, y = tile
    target = output_dir / str(level) / str(x) / f"{y}.jpg"
    if target.exists() and target.stat().st_size > 100:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        ESRI_URL.format(z=level, x=x, y=y),
        headers={"User-Agent": "cesium-track-video/0.1 (local imagery cache)"},
    )
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
            if not content.startswith(b"\xff\xd8"):
                raise ValueError("response is not a JPEG")
            temporary = target.with_suffix(".jpg.part")
            temporary.write_bytes(content)
            temporary.replace(target)
            return True
        except Exception as error:
            last_error = error
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"影像下载失败 z={level} x={x} y={y}: {last_error}")


def prepare_imagery(bounds: list[float], output_dir: Path, min_level: int = 8, max_level: int = 14, workers: int = 8):
    tiles = imagery_tiles(bounds, min_level, max_level)
    missing = [tile for tile in tiles if not (output_dir / str(tile[0]) / str(tile[1]) / f"{tile[2]}.jpg").exists()]
    downloaded = 0
    if missing:
        print(f"下载 Esri 卫星影像: 缺少 {len(missing)}/{len(tiles)} ...", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(download_tile, tile, output_dir) for tile in missing]
            for index, future in enumerate(as_completed(futures), 1):
                if future.result():
                    downloaded += 1
                if index % 25 == 0 or index == len(futures):
                    print(f"影像缓存 {index}/{len(futures)}", flush=True)
    return {"tile_count": len(tiles), "downloaded": downloaded, "min_level": min_level, "max_level": max_level}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bounds", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"), required=True)
    parser.add_argument("--output", type=Path, default=Path("web/imagery"))
    parser.add_argument("--min-level", type=int, default=8)
    parser.add_argument("--max-level", type=int, default=14)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    print(prepare_imagery(args.bounds, args.output, args.min_level, args.max_level, args.workers))


if __name__ == "__main__":
    main()
