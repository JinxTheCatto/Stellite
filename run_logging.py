import glob
import os
import re
import threading
import time
from pathlib import Path


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


RUN_FILES = ("stellite-*.txt", "sightings-*.csv", "stellite-screen-*.mp4", "stellite-screen-*.log")
KEPT_RECORDINGS = 3 # screen recordings of the last run that are kept, they are a few hundred MB each


def run_played(log_path):
    # a run that pressed keys is worth keeping for a look afterwards, one that was only opened and closed is not
    try:
        with open(log_path, encoding="utf-8", errors="replace") as file:
            text = file.read()
    except OSError:
        return False
    return "Pressing " in text or "Holding " in text


def clear_old_runs(data):
    # Every start clears the logs and screen recordings from earlier runs. The last run that played is not lost: its
    # log, the notes it saw and its newest recordings move to data/last_run, in place of the run kept there before,
    # so it can still be looked at after a restart. Only stellite's own files are touched.
    # Returns how many files were deleted and how many were kept
    kept_folder = os.path.join(data, "last_run")
    old = [path for folder in ("logs", "recordings") for pattern in RUN_FILES for path in glob.glob(os.path.join(data, folder, pattern))]
    keep = any(run_played(path) for path in old if path.endswith(".txt"))
    recordings = sorted((path for path in old if path.endswith(".mp4")), key=lambda path: os.path.getmtime(path) if os.path.exists(path) else 0.0, reverse=True)
    spare = {os.path.splitext(path)[0] for path in recordings[KEPT_RECORDINGS:]} # older recordings go, with their ffmpeg logs
    removed = kept = 0
    if keep:
        os.makedirs(kept_folder, exist_ok=True)
        for pattern in RUN_FILES:
            for path in glob.glob(os.path.join(kept_folder, pattern)):
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
    for path in old:
        try:
            if keep and os.path.splitext(path)[0] not in spare:
                os.replace(path, os.path.join(kept_folder, os.path.basename(path)))
                kept += 1
            else:
                os.remove(path)
                removed += 1
        except OSError:
            pass # still open somewhere, leave it for the next start
    return removed, kept


def format_skipped_key(key, late, clock=time.time):
    return f"{clock()}: Skipped chart key {key.upper()} (scheduler was {late * 1000:.0f} ms late)"


class SessionLog:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = directory / f"stellite-{timestamp}-{time.time_ns() % 1_000_000_000:09d}.txt"
        self._file = self.path.open("x", encoding="utf-8", newline="\n")
        self._lock = threading.Lock()
        self.write(f"Stellite session started: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    def write(self, message):
        text = ANSI_ESCAPE_RE.sub("", str(message)).replace("\r", "")
        with self._lock:
            self._file.write(text)
            if not text.endswith("\n"):
                self._file.write("\n")
            self._file.flush()

    def close(self):
        with self._lock:
            self._file.close()


class ManualKeyLogger:
    def __init__(self, keys, enabled, log, clock=time.time):
        self._keys = {key.lower() for key in keys}
        self._enabled = enabled
        self._log = log
        self._clock = clock
        self._held = set()
        self._lock = threading.Lock()

    def handle(self, event):
        key = str(getattr(event, "name", "")).lower()
        if key not in self._keys:
            return

        with self._lock:
            if event.event_type == "up":
                self._held.discard(key)
                return
            if event.event_type != "down" or key in self._held:
                return
            self._held.add(key)
            if not self._enabled():
                return

        self._log(f"{self._clock()}: Manual key press {key.upper()}")
