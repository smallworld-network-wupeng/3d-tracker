import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from compose_media_video import fit_popup_geometry, load_segment_list


class ComposeMediaVideoTests(unittest.TestCase):
    def test_landscape_canvas_with_portrait_child(self):
        self.assertEqual(fit_popup_geometry(1080, 1920, 720, 480), (270, 480))

    def test_landscape_canvas_with_landscape_child(self):
        self.assertEqual(fit_popup_geometry(1920, 1080, 720, 480), (720, 404))

    def test_portrait_canvas_with_portrait_child(self):
        self.assertEqual(fit_popup_geometry(1080, 1920, 972, 1104), (620, 1104))

    def test_portrait_canvas_with_landscape_child(self):
        self.assertEqual(fit_popup_geometry(1920, 1080, 972, 1104), (972, 546))

    def test_popup_geometry_uses_both_bounds_for_square_video(self):
        self.assertEqual(fit_popup_geometry(1080, 1080, 720, 480), (480, 480))

    def test_creation_time_override_allows_video_without_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "insta360.MP4"
            video.touch()
            segment_list = root / "video_segments.json"
            segment_list.write_text(json.dumps({
                "schema_version": 1,
                "videos": [{
                    "file": "insta360.MP4",
                    "creation_time": "2026-08-23T08:12:35",
                    "segments": [{"start_seconds": 2, "end_seconds": 8}],
                }],
            }), encoding="utf-8")
            with patch(
                "compose_media_video.probe",
                return_value={"path": video, "created": None, "duration": 10.0},
            ) as mocked_probe:
                segments, errors, warnings = load_segment_list(segment_list, root)

            mocked_probe.assert_called_once_with(video, require_creation_time=False)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])
            self.assertEqual(segments[0]["source_created"], datetime(2026, 8, 23, 8, 12, 35))
            self.assertEqual(segments[0]["created"], datetime(2026, 8, 23, 8, 12, 37))


if __name__ == "__main__":
    unittest.main()
