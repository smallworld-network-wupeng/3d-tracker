#!/usr/bin/env python3
"""Cache AWS Terrarium SRTM tiles around a WGS84 bounding box."""

from __future__ import annotations

import argparse
import math
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


TERRARIUM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"


def lon_lat_to_tile(lon: float, lat: float, level: int) -> tuple[int, int]:
    count = 2**level
    latitude = max(-85.05112878, min(85.05112878, lat))
    x = int((lon + 180.0) / 360.0 * count)
    y = int((1.0 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2.0 * count)
    return max(0, min(count - 1, x)), max(0, min(count - 1, y))


def tile_list(bounds: list[float], max_level: int, padding: int = 3) -> list[tuple[int, int, int]]:
    west, south, east, north = bounds
    tiles = []
    for level in range(max_level + 1):
        southwest = lon_lat_to_tile(west, south, level)
        northeast = lon_lat_to_tile(east, north, level)
        count = 2**level
        level_padding = padding if level >= 8 else 0
        min_x = max(0, min(southwest[0], northeast[0]) - level_padding)
        max_x = min(count - 1, max(southwest[0], northeast[0]) + level_padding)
        min_y = max(0, min(southwest[1], northeast[1]) - level_padding)
        max_y = min(count - 1, max(southwest[1], northeast[1]) + level_padding)
        tiles.extend((level, x, y) for x in range(min_x, max_x + 1) for y in range(min_y, max_y + 1))
    return tiles


def download_tile(tile: tuple[int, int, int], output_dir: Path, retries: int = 3) -> bool:
    level, x, y = tile
    target = output_dir / str(level) / str(x) / f"{y}.png"
    if target.exists() and target.stat().st_size > 100:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        TERRARIUM_URL.format(z=level, x=x, y=y),
        headers={"User-Agent": "cesium-track-video/0.1 (local terrain cache)"},
    )
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
            if not content.startswith(b"\x89PNG"):
                raise ValueError("response is not a PNG")
            temporary = target.with_suffix(".png.part")
            temporary.write_bytes(content)
            temporary.replace(target)
            return True
        except Exception as error:
            last_error = error
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"DEM 下载失败 z={level} x={x} y={y}: {last_error}")


def prepare_terrain(bounds: list[float], output_dir: Path, max_level: int = 14, workers: int = 8) -> dict:
    tiles = tile_list(bounds, max_level)
    missing = [tile for tile in tiles if not (output_dir / str(tile[0]) / str(tile[1]) / f"{tile[2]}.png").exists()]
    downloaded = 0
    if missing:
        print(f"下载 SRTM 地形瓦片: 缺少 {len(missing)}/{len(tiles)} ...", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(download_tile, tile, output_dir) for tile in missing]
            for index, future in enumerate(as_completed(futures), 1):
                if future.result():
                    downloaded += 1
                if index % 25 == 0 or index == len(futures):
                    print(f"地形缓存 {index}/{len(futures)}", flush=True)
    return {"tile_count": len(tiles), "downloaded": downloaded, "max_level": max_level}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bounds", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"), required=True)
    parser.add_argument("--output", type=Path, default=Path("web/terrain"))
    parser.add_argument("--max-level", type=int, default=14)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    print(prepare_terrain(args.bounds, args.output, args.max_level, args.workers))


if __name__ == "__main__":
    main()
