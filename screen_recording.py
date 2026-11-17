import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


class ScreenRecorder:
    def __init__(self, recordings_dir):
        self.recordings_dir = Path(recordings_dir)
        self.process = None
        self.output_path = None
        self.log_path = None
        self.log_file = None

    @staticmethod
    def _find_ffmpeg():
        executable = shutil.which("ffmpeg")
        if executable:
            return executable

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            candidates = [
                binary
                for package in packages.glob("Gyan.FFmpeg_*")
                for build in package.glob("ffmpeg-*")
                for binary in (build / "bin" / "ffmpeg.exe",)
                if binary.is_file()
            ]
            if candidates:
                return str(max(candidates, key=lambda path: path.stat().st_mtime))

        raise FileNotFoundError("FFmpeg was not found on PATH or in the WinGet FFmpeg package")

    # GDI capture, desktop duplication (ddagrab) froze the game picture for ~14 s when it started and blinded the screen reader
    # a GPU encoder does the heavy part, the CPU fallback is only for PCs without one
    CAPTURE_INPUT = ["-f", "gdigrab", "-framerate", "30", "-draw_mouse", "1", "-i", "desktop"]
    GPU_ENCODERS = (
        ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0", "-pix_fmt", "yuv420p"]),
        ("h264_amf", ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23", "-pix_fmt", "nv12"]),
        ("h264_qsv", ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "23", "-pix_fmt", "nv12"]),
    )
    CPU_ENCODER = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p"]

    def _capture_args(self, executable):
        cached = getattr(self, "_capture", None)
        if cached is not None:
            return cached
        self._capture = self.CAPTURE_INPUT + self.CPU_ENCODER
        for name, encode in self.GPU_ENCODERS:
            test = [executable, "-hide_banner", "-loglevel", "error"] + self.CAPTURE_INPUT + ["-frames:v", "2"] + encode + ["-f", "null", "-"]
            try:
                result = subprocess.run(test, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception: # a broken or missing encoder just means trying the next one
                continue
            if getattr(result, "returncode", 1) == 0:
                self._capture = self.CAPTURE_INPUT + encode
                break
        return self._capture

    def start(self, song_name):
        if self.process is not None:
            if self.process.poll() is None:
                return None
            self.stop()

        executable = self._find_ffmpeg()
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", song_name).strip("._-") or "song"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.output_path = self.recordings_dir / f"stellite-screen-{timestamp}-{slug}.mp4"
        self.log_path = self.output_path.with_suffix(".log")
        self.log_file = self.log_path.open("wb")
        command = [executable, "-hide_banner", "-loglevel", "error", "-y"] + self._capture_args(executable) + ["-an", str(self.output_path)]
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self.log_file,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            self.log_file.close()
            self.log_file = None
            log_path = self.log_path
            self.output_path = None
            self.log_path = None
            if log_path is not None and log_path.exists() and log_path.stat().st_size == 0:
                log_path.unlink()
            raise

        if self.process.poll() is not None:
            log_path = self.log_path
            self.stop()
            raise RuntimeError(f"FFmpeg exited immediately; see {log_path}")
        return self.output_path

    def stop(self):
        if self.process is None:
            return None

        process = self.process
        output_path = self.output_path
        log_path = self.log_path
        log_file = self.log_file
        self.process = None
        self.output_path = None
        self.log_path = None
        self.log_file = None

        if process.poll() is None:
            if process.stdin is not None:
                try:
                    process.stdin.write(b"q\n")
                    process.stdin.flush()
                except BrokenPipeError:
                    pass
                finally:
                    process.stdin.close()
            try:
                return_code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                return_code = process.wait(timeout=5)
        else:
            if process.stdin is not None:
                process.stdin.close()
            return_code = process.wait()

        if log_file is not None:
            log_file.close()

        if return_code != 0:
            details = ""
            if log_path is not None and log_path.exists():
                details = log_path.read_text(encoding="utf-8", errors="replace").strip()
            suffix = f": {details}" if details else ""
            raise RuntimeError(f"FFmpeg exited with code {return_code}{suffix}; see {log_path}")

        if log_path is not None and log_path.exists() and log_path.stat().st_size == 0:
            try:
                log_path.unlink()
            except OSError:
                pass # windows can hold the empty log a moment longer, the next start cleans it up
        return output_path
