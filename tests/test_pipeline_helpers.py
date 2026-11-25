import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mix_music import has_audio


class PipelineHelperTests(unittest.TestCase):
    @patch("mix_music.subprocess.run")
    def test_has_audio_detects_stream(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps({"streams": [{"index": 1}]}), "")
        self.assertTrue(has_audio(Path("movie.mp4")))

    @patch("mix_music.subprocess.run")
    def test_has_audio_accepts_silent_video(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps({"streams": []}), "")
        self.assertFalse(has_audio(Path("movie.mp4")))


if __name__ == "__main__":
    unittest.main()
