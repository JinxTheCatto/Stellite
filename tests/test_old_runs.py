import os
import tempfile
import time
import unittest

import run_logging


def put(folder, name, text="x", age=0.0):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


class OldRunsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.data = self.folder.name
        self.logs = os.path.join(self.data, "logs")
        self.recordings = os.path.join(self.data, "recordings")
        self.kept = os.path.join(self.data, "last_run")

    def tearDown(self):
        self.folder.cleanup()

    def names(self, folder):
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def test_the_last_run_that_played_is_kept_for_a_look_after_a_restart(self):
        put(self.logs, "stellite-1.txt", "Stellite session started\n1.0: Pressing K (chart)\n")
        put(self.logs, "sightings-1.csv")
        put(self.recordings, "stellite-screen-1-song.mp4")
        put(self.recordings, "stellite-screen-1-song.log")
        removed, kept = run_logging.clear_old_runs(self.data)
        self.assertEqual((removed, kept), (0, 4))
        self.assertEqual(self.names(self.logs), [])
        self.assertEqual(self.names(self.recordings), [])
        self.assertEqual(self.names(self.kept), ["sightings-1.csv", "stellite-1.txt", "stellite-screen-1-song.log", "stellite-screen-1-song.mp4"])

    def test_a_run_that_never_played_does_not_push_out_the_one_that_is_kept(self):
        put(self.kept, "stellite-1.txt", "1.0: Pressing K (chart)\n")
        put(self.logs, "stellite-2.txt", "Stellite session started\n") # opened and closed again
        removed, kept = run_logging.clear_old_runs(self.data)
        self.assertEqual((removed, kept), (1, 0))
        self.assertEqual(self.names(self.kept), ["stellite-1.txt"])
        self.assertEqual(self.names(self.logs), [])

    def test_the_next_run_that_played_takes_its_place(self):
        put(self.kept, "stellite-1.txt", "1.0: Pressing K (chart)\n")
        put(self.kept, "stellite-screen-1-old.mp4")
        put(self.logs, "stellite-2.txt", "2.0: Holding D (chart)\n")
        run_logging.clear_old_runs(self.data)
        self.assertEqual(self.names(self.kept), ["stellite-2.txt"])

    def test_only_the_newest_recordings_of_a_long_run_are_kept(self):
        put(self.logs, "stellite-1.txt", "1.0: Pressing K\n")
        for index in range(6):
            put(self.recordings, f"stellite-screen-{index}.mp4", age=600 - 100 * index) # 5 is the newest
            put(self.recordings, f"stellite-screen-{index}.log", age=600 - 100 * index)
        run_logging.clear_old_runs(self.data)
        self.assertEqual(self.names(self.recordings), [])
        self.assertEqual(self.names(self.kept), [
            "stellite-1.txt",
            "stellite-screen-3.log", "stellite-screen-3.mp4",
            "stellite-screen-4.log", "stellite-screen-4.mp4",
            "stellite-screen-5.log", "stellite-screen-5.mp4",
        ])

    def test_other_files_are_left_alone(self):
        put(self.logs, "stellite-1.txt", "1.0: Pressing K\n")
        put(self.logs, "ready-screen-part.png")
        put(self.kept, "notes.md")
        run_logging.clear_old_runs(self.data)
        self.assertEqual(self.names(self.logs), ["ready-screen-part.png"])
        self.assertEqual(self.names(self.kept), ["notes.md", "stellite-1.txt"])


if __name__ == "__main__":
    unittest.main()
