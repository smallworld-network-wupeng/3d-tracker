import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image

from app_config import build_project_config
from compose_media_video import load_photos, plan_media_events
from photo_events import (
    PHOTO_LIST, PhotoEvent, load_photo_image, read_capture_time, read_photo_events,
    register_heif, write_photo_events,
)


def photo_exif():
    exif = Image.Exif()
    exif[274] = 6
    exif[34665] = {36867: "2026:08:23 00:12:35", 36881: "+00:00", 37521: "250"}
    return exif


class PhotoEventsTests(unittest.TestCase):
    def test_jpeg_exif_timezone_subseconds_and_rotation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "oriented.JPG"
            Image.new("RGB", (50, 30)).save(path, exif=photo_exif())
            self.assertEqual(read_capture_time(path), datetime(2026, 8, 23, 8, 12, 35, 250000))
            self.assertEqual(load_photo_image(path, 80).size, (30, 50))

    def test_heic_uses_primary_image_and_capture_time(self):
        from pillow_heif import from_pillow

        register_heif()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "apple.HEIC"
            container = from_pillow(Image.new("RGB", (32, 32), "gray"))
            original = Image.new("RGB", (32, 64), "coral")
            exif = photo_exif()
            exif[274] = 1
            original.info["exif"] = exif.tobytes()
            container.add_from_pillow(original)
            container.save(path, primary_index=1)
            self.assertEqual(read_capture_time(path), datetime(2026, 8, 23, 8, 12, 35, 250000))
            self.assertEqual(load_photo_image(path, 80).size, (32, 64))

    def test_png_transparency_and_manual_times(self):
        start = datetime(2026, 8, 23, 8)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            png = directory / "雪山.PNG"
            Image.new("RGBA", (16, 16), (255, 0, 0, 0)).save(png)
            self.assertEqual(load_photo_image(png, 80).getpixel((0, 0)), (0, 0, 0))
            self.assertIsNone(read_capture_time(png))
            Image.new("RGB", (16, 16)).save(directory / "Outside.jpg")
            events = [
                PhotoEvent(png.name, True, "2026-08-23 08:10:00", 2.5, "fill"),
                PhotoEvent("Outside.jpg", True, "2026-08-23 09:10:00"),
                PhotoEvent("Disabled.png"),
            ]
            path = directory / PHOTO_LIST
            write_photo_events(path, events)
            self.assertEqual(read_photo_events(path), events)
            photos, errors, warnings = load_photos(path, directory, start, start + timedelta(hours=1))
            self.assertEqual(errors, [])
            self.assertIn("Outside.jpg", warnings[0])
            self.assertEqual([(photo["path"], photo["duration"]) for photo in photos], [(png, 2.5)])

    def test_timeline_splits_video_group_and_keeps_ties_deterministic(self):
        start = datetime(2026, 8, 23, 8)
        at = start + timedelta(minutes=5)
        groups = [(1, [
            {"path": Path("before.mp4"), "created": start, "duration": 1},
            {"path": Path("same.mp4"), "created": at, "duration": 1},
            {"path": Path("after.mp4"), "created": at + timedelta(seconds=1), "duration": 1},
        ])]
        photos = [
            {"path": Path(name), "created": at, "duration": 5, "framing": "fit"}
            for name in ("b.heic", "a.png")
        ]
        planned = plan_media_events(groups, photos, start, start + timedelta(minutes=10), 30, {}, 30)
        self.assertEqual([event["files"] for event, _ in planned], [
            ["before.mp4"], ["same.mp4"], ["a.png"], ["b.heic"], ["after.mp4"],
        ])
        self.assertEqual(planned[1][0]["base_time"], planned[2][0]["base_time"])
        self.assertEqual(planned[2][0]["base_time"], planned[3][0]["base_time"])
        self.assertEqual(planned[2][0]["track_progress"], 0.5)

    def test_saved_end_placement_follows_the_final_video_clip_before_later_photos(self):
        start = datetime(2026, 8, 23, 8)
        end = start + timedelta(hours=1)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            photo = directory / "finish.jpg"
            Image.new("RGB", (16, 16)).save(photo)
            later = directory / "later.jpg"
            Image.new("RGB", (16, 16)).save(later)
            events = [
                PhotoEvent(photo.name, True, "2026-08-24 08:00:00", placement="end"),
                PhotoEvent(later.name, True, "2026-08-23 08:55:00"),
            ]
            write_photo_events(directory / PHOTO_LIST, events)
            photos, errors, warnings = load_photos(directory / PHOTO_LIST, directory, start, end)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])
            self.assertEqual(photos[0]["placement"], "end")

            groups = [
                (1, [{"path": Path("early.mp4"), "created": start, "duration": 1}]),
                (2, [{"path": Path("last.mp4"), "created": start + timedelta(minutes=50), "duration": 1}]),
            ]
            planned = plan_media_events(groups, photos, start, end, 30, {}, 30)
            self.assertEqual([event["files"] for event, _ in planned], [
                ["early.mp4"], ["last.mp4"], [str(photo)], [str(later)],
            ])
            candidate = planned[2][0]
            self.assertEqual(candidate["placement"], "end")
            self.assertEqual(candidate["base_time"], planned[1][0]["base_time"])
            self.assertEqual(candidate["track_progress"], planned[1][0]["track_progress"])
            self.assertLess(candidate["base_time"], planned[3][0]["base_time"])
            self.assertLess(candidate["base_time"], 30)
            without_videos = plan_media_events([], photos, start, end, 30, {}, 30)
            self.assertEqual([event["file"] for event, _ in without_videos], [later.name])

    def test_photo_only_config_ignores_unselected_video_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            track = directory / "route.kml"
            track.touch()
            config, output = build_project_config(
                track_file=track, activity_name="Route", orientation="landscape",
                quality="720p", seconds=30, output_directory=directory,
                media_directory=directory,
                photo_directory=directory,
                photo_events=[{
                    "file": "photo.jpg", "enabled": True, "capture_time": None,
                    "duration": 5.0, "framing": "fit",
                }],
            )
            self.assertTrue(config["media"]["enabled"])
            self.assertEqual(config["media"]["directory"], "")
            self.assertEqual(config["media"]["photos"][0]["file"], "photo.jpg")
            self.assertNotIn("photo_list", config["media"])
            self.assertEqual(config["media"]["output"], str(output))
            self.assertNotEqual(config["render"]["output"], str(output))
