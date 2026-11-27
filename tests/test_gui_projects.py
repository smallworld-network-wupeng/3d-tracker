import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_config import Segment, build_editor_project, write_editor_project
from gui_app import MainWindow


class ProjectInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_open_project_button_restores_saved_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path = root / "saved-project.3dtrack"
            document = build_editor_project(
                project_path=project_path,
                track_file=root / "activity.fit",
                activity_name="Saved activity",
                orientation="portrait",
                quality="720p",
                seconds=45,
                output_directory=root / "output",
                media_directory=root / "videos",
                segments=[Segment("clip.mp4", 1.5, 4.0, "2026-08-23T08:12:35")],
                photo_directory=root / "photos",
                photo_events=[{
                    "file": "summit.jpg",
                    "enabled": True,
                    "capture_time": "2026-08-23 09:00:00",
                    "duration": 5.0,
                    "framing": "fit",
                    "placement": "end",
                }],
                music_file=root / "music.mp3",
                music_start_offset_seconds=3.5,
            )
            write_editor_project(project_path, document)

            window = MainWindow()
            self.addCleanup(window.close)
            window.show()
            self.app.processEvents()

            self.assertTrue(window.open_project_button.isVisible())
            self.assertEqual(window.open_project_button.objectName(), "openProjectButton")
            with patch(
                "gui_app.QFileDialog.getOpenFileName",
                return_value=(str(project_path), "3D Track projects (*.3dtrack)"),
            ):
                window.open_project_button.click()

            self.assertEqual(window.project_path, project_path.resolve())
            self.assertEqual(window.track_edit.text(), str((root / "activity.fit").resolve()))
            self.assertEqual(window.name_edit.text(), "Saved activity")
            self.assertEqual(window.orientation.value(), "portrait")
            self.assertEqual(window.quality.value(), "720p")
            self.assertIn("45", window.duration_combo.currentText())
            self.assertEqual(window.segments, [
                Segment("clip.mp4", 1.5, 4.0, "2026-08-23T08:12:35")
            ])
            self.assertEqual(window.photo_events[0].file, "summit.jpg")
            self.assertEqual(window.photo_events[0].placement, "end")
            self.assertEqual(window.music_start_offset.value(), 3.5)
            self.assertIn("saved-project", window.windowTitle())


if __name__ == "__main__":
    unittest.main()
