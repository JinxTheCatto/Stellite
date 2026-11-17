import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from screen_recording import ScreenRecorder


class ScreenRecorderTests(unittest.TestCase):
    def test_prefers_gpu_capture_when_an_encoder_works(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            process.wait.return_value = 0
            process.stdin = Mock()
            recorder = ScreenRecorder(directory)
            with patch("screen_recording.shutil.which", return_value="ffmpeg"), patch(
                "screen_recording.subprocess.Popen",
                return_value=process,
            ) as popen, patch("screen_recording.subprocess.run", return_value=Mock(returncode=0)):
                recorder.start("Enemy")

            command = popen.call_args.args[0]
            # plain screen capture, desktop duplication froze the game when it started
            self.assertIn("gdigrab", command)
            self.assertNotIn("lavfi", command)
            self.assertEqual(command[command.index("-framerate") + 1], "30")
            self.assertIn("h264_nvenc", command)
            self.assertNotIn("libx264", command)
            recorder.stop()

    def test_falls_back_to_light_cpu_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            process.wait.return_value = 0
            process.stdin = Mock()
            recorder = ScreenRecorder(directory)
            with patch("screen_recording.shutil.which", return_value="ffmpeg"), patch(
                "screen_recording.subprocess.Popen",
                return_value=process,
            ) as popen, patch("screen_recording.subprocess.run", return_value=Mock(returncode=1)):
                output_path = recorder.start("Die With A Smile")

            command = popen.call_args.args[0]
            # no GPU encoder in the test (the probe is mocked to fail), so it uses the light CPU fallback
            self.assertIn("gdigrab", command)
            self.assertIn("desktop", command)
            self.assertEqual(command[command.index("-framerate") + 1], "30")
            self.assertIn("libx264", command)
            self.assertEqual(command[command.index("-crf") + 1], "28")
            self.assertTrue(str(output_path).endswith(".mp4"))
            self.assertIn("Die_With_A_Smile", os.path.basename(output_path))
            recorder.stop()

    def test_stops_capture_and_finalizes_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            process.stdin = Mock()
            process.wait.return_value = 0
            recorder = ScreenRecorder(directory)
            with patch("screen_recording.shutil.which", return_value="ffmpeg"), patch(
                "screen_recording.subprocess.Popen",
                return_value=process,
            ):
                output_path = recorder.start("Test Song")
                stopped_path = recorder.stop()

            process.stdin.write.assert_called_once_with(b"q\n")
            process.wait.assert_called_once_with(timeout=10)
            self.assertEqual(stopped_path, output_path)
            self.assertFalse(output_path.with_suffix(".log").exists())

    def test_reports_missing_ffmpeg(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = ScreenRecorder(directory)
            with patch("screen_recording.shutil.which", return_value=None), patch.dict(
                os.environ,
                {"LOCALAPPDATA": ""},
            ), self.assertRaises(FileNotFoundError):
                recorder.start("Test Song")


if __name__ == "__main__":
    unittest.main()
