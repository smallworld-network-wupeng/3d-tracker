import json
import tempfile
import unittest
from pathlib import Path

from app_config import (
    Segment,
    build_project_config,
    format_timecode,
    normalize_creation_time,
    output_dimensions,
    parse_timecode,
    popup_safe_bounds,
    read_segment_list,
    write_project_config,
    write_segment_list,
)


class AppConfigTests(unittest.TestCase):
    def test_timecode_round_trip(self):
        value = 3 * 3600 + 7 * 60 + 12.345
        self.assertAlmostEqual(parse_timecode(format_timecode(value)), value, places=3)
        self.assertEqual(parse_timecode("01:30.5"), 90.5)

    def test_segment_list_allows_multiple_intervals_per_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "video_segments.txt"
            expected = [
                Segment("GX010001.MP4", 5.0, 8.5),
                Segment("GX010001.MP4", 12.0, 19.0),
                Segment("GX020001.MP4", 1.0, 3.0),
            ]
            write_segment_list(path, expected)
            self.assertEqual(read_segment_list(path), expected)

    def test_segment_list_round_trips_creation_time_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "video_segments.txt"
            expected = [
                Segment("insta360.MP4", 2.5, 8.0, "2026-08-23T08:12:35"),
            ]
            write_segment_list(path, expected)
            self.assertIn("2026-08-23T08:12:35", path.read_text(encoding="utf-8"))
            self.assertEqual(read_segment_list(path), expected)

    def test_creation_time_accepts_editor_format(self):
        self.assertEqual(
            normalize_creation_time("2026-08-23 08:12:35"),
            "2026-08-23T08:12:35",
        )
        self.assertEqual(
            normalize_creation_time("2026-08-23T08:12:35+08:00"),
            "2026-08-23T08:12:35",
        )

    def test_dimensions(self):
        self.assertEqual(output_dimensions("landscape", "720p"), (1280, 720))
        self.assertEqual(output_dimensions("portrait", "1080p"), (1080, 1920))

    def test_popup_bounds_scale_with_canvas_orientation(self):
        self.assertEqual(popup_safe_bounds(1280, 720), (720, 480))
        self.assertEqual(popup_safe_bounds(1920, 1080), (1080, 720))
        self.assertEqual(popup_safe_bounds(1080, 1920), (972, 1104))
        self.assertEqual(popup_safe_bounds(720, 1280), (648, 736))

    def test_build_config_uses_hidden_portrait_preset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            track = root / "activity.fit"
            track.touch()
            config, output = build_project_config(
                track_file=track,
                activity_name="测试活动",
                orientation="portrait",
                quality="1080p",
                seconds=30,
                output_directory=root / "output",
            )
            self.assertEqual(config["render"]["width"], 1080)
            self.assertEqual(config["render"]["height"], 1920)
            self.assertEqual(config["render"]["camera_range_m"], 11500.0)
            self.assertTrue(config["render"]["auto_camera_range"])
            self.assertEqual(config["render"]["camera_min_range_m"], 3000.0)
            self.assertEqual(config["render"]["camera_fit_vertical"], 0.62)
            self.assertEqual(config["render"]["camera_screen_y"], 0.08)
            self.assertEqual(config["media"]["popup_width"], 972)
            self.assertEqual(config["media"]["popup_height"], 1104)
            self.assertFalse(config["media"]["enabled"])
            self.assertEqual(Path(config["render"]["output"]), output)

    def test_project_config_is_utf8_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "项目.json"
            write_project_config(path, {"name": "峨眉山"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["name"], "峨眉山")


if __name__ == "__main__":
    unittest.main()
