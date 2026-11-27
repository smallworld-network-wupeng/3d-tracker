import json
import tempfile
import unittest
from pathlib import Path

from app_config import (
    Segment,
    build_editor_project,
    build_project_config,
    format_timecode,
    list_video_files,
    normalize_creation_time,
    output_dimensions,
    parse_timecode,
    popup_safe_bounds,
    read_editor_project,
    read_segment_list,
    write_project_config,
    write_editor_project,
    write_segment_list,
)


class AppConfigTests(unittest.TestCase):
    def test_video_list_excludes_dotfiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("GX010002.MOV", "GX010001.MP4", "._GX010001.MP4", ".hidden.m4v"):
                (root / name).touch()

            self.assertEqual(
                [path.name for path in list_video_files(root)],
                ["GX010001.MP4", "GX010002.MOV"],
            )

    def test_timecode_round_trip(self):
        value = 3 * 3600 + 7 * 60 + 12.345
        self.assertAlmostEqual(parse_timecode(format_timecode(value)), value, places=3)
        self.assertEqual(parse_timecode("01:30.5"), 90.5)

    def test_segment_list_allows_multiple_intervals_per_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "video_segments.json"
            expected = [
                Segment("GX010001.MP4", 5.0, 8.5),
                Segment("GX010001.MP4", 12.0, 19.0),
                Segment("GX020001.MP4", 1.0, 3.0),
            ]
            write_segment_list(path, expected)
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["schema_version"], 1)
            self.assertEqual(len(document["videos"]), 2)
            self.assertEqual(len(document["videos"][0]["segments"]), 2)
            self.assertEqual(read_segment_list(path), expected)

    def test_segment_list_round_trips_creation_time_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "video_segments.json"
            expected = [
                Segment("insta360.MP4", 2.5, 8.0, "2026-08-23T08:12:35"),
            ]
            write_segment_list(path, expected)
            self.assertIn("2026-08-23T08:12:35", path.read_text(encoding="utf-8"))
            self.assertEqual(read_segment_list(path), expected)

    def test_segment_list_rejects_unknown_schema_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "video_segments.json"
            path.write_text('{"schema_version": 2, "videos": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "不支持的片段配置版本"):
                read_segment_list(path)

    def test_segment_list_allows_extension_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "video_segments.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "project_note": "future top-level field",
                "videos": [{
                    "file": "clip.MP4",
                    "camera": "future video field",
                    "segments": [{
                        "start_seconds": 1,
                        "end_seconds": 2,
                        "label": "future segment field",
                    }],
                }],
            }), encoding="utf-8")
            self.assertEqual(read_segment_list(path), [Segment("clip.MP4", 1.0, 2.0)])

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

    def test_editor_project_round_trips_all_editing_state_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path = root / "峨眉山.3dtrack"
            track = root / "assets" / "activity.fit"
            video = root / "assets" / "video"
            photos = root / "assets" / "photos"
            music = root / "assets" / "music.mp3"
            output = root / "output"
            document = build_editor_project(
                project_path=project_path,
                track_file=track,
                activity_name="峨眉山",
                orientation="portrait",
                quality="1080p",
                seconds=45,
                output_directory=output,
                media_directory=video,
                segments=[Segment("clip.mp4", 1.5, 4.0, "2026-08-23T08:12:35")],
                photo_directory=photos,
                photo_events=[{
                    "file": "summit.jpg", "enabled": True,
                    "capture_time": "2026-08-23 09:00:00", "duration": 5.0,
                    "framing": "fit", "placement": "end",
                }],
                music_file=music,
                music_start_offset_seconds=3.5,
            )
            self.assertEqual(document["track"]["file"], "assets/activity.fit")
            self.assertEqual(document["video"]["directory"], "assets/video")
            write_editor_project(project_path, document)
            loaded = read_editor_project(project_path)
            self.assertEqual(loaded["track"]["file"], str(track.resolve()))
            self.assertEqual(loaded["video"]["segments"], [
                Segment("clip.mp4", 1.5, 4.0, "2026-08-23T08:12:35")
            ])
            self.assertEqual(loaded["photos"]["events"][0]["file"], "summit.jpg")
            self.assertEqual(loaded["photos"]["events"][0]["placement"], "end")
            self.assertEqual(loaded["music"]["start_offset_seconds"], 3.5)

    def test_build_config_uses_music_start_offset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            track = root / "activity.fit"
            track.touch()
            music = root / "music.mp3"
            music.touch()
            config, _ = build_project_config(
                track_file=track,
                activity_name="测试活动",
                orientation="landscape",
                quality="1080p",
                seconds=30,
                output_directory=root / "output",
                music_file=music,
                music_start_offset_seconds=3.5,
            )
            self.assertTrue(config["music"]["enabled"])
            self.assertEqual(config["music"]["start_offset_seconds"], 3.5)

    def test_build_config_embeds_video_edits_without_a_sidecar_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            track = root / "activity.fit"
            track.touch()
            videos = root / "videos"
            videos.mkdir()
            segment = Segment("clip.mp4", 1.0, 3.5, "2026-08-23T08:12:35")
            config, _ = build_project_config(
                track_file=track,
                activity_name="测试活动",
                orientation="landscape",
                quality="720p",
                seconds=30,
                output_directory=root / "output",
                media_directory=videos,
                segments=[segment],
            )
            self.assertTrue(config["media"]["enabled"])
            self.assertEqual(config["media"]["segments"], [{
                "file": "clip.mp4",
                "start_seconds": 1.0,
                "end_seconds": 3.5,
                "creation_time": "2026-08-23T08:12:35",
            }])
            self.assertNotIn("segment_list", config["media"])


if __name__ == "__main__":
    unittest.main()
