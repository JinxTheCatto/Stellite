import re
import unicodedata
from difflib import SequenceMatcher


class TimingTuner:
    def __init__(self, initial_offset_ms, batch_size=12, step_ms=5):
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if step_ms < 1:
            raise ValueError("step_ms must be positive")
        self.baseline_offset_ms = float(initial_offset_ms)
        self.batch_size = batch_size
        self.step_ms = step_ms
        self.offsets = (
            self.baseline_offset_ms,
            self.baseline_offset_ms - step_ms,
            self.baseline_offset_ms + step_ms,
        )
        self.stage = 0
        self.results = {offset: {"perfect": 0, "good": 0} for offset in self.offsets}
        self.finished = False
        self.selected_offset_ms = self.baseline_offset_ms

    @property
    def current_offset_ms(self):
        return self.offsets[self.stage]

    def observe(self, grade):
        if self.finished or grade not in ("perfect", "good"):
            return None

        result = self.results[self.current_offset_ms]
        result[grade] += 1
        if result["perfect"] + result["good"] < self.batch_size:
            return None

        if self.stage == 0 and result["good"] == 0:
            self.finished = True
            return {
                "offset_ms": self.baseline_offset_ms,
                "phase": "complete",
                "save": False,
                "reason": "all_perfect",
            }

        if self.stage < len(self.offsets) - 1:
            self.stage += 1
            return {
                "offset_ms": self.current_offset_ms,
                "phase": "trial",
                "save": False,
                "reason": "compare",
            }

        def score(offset):
            counts = self.results[offset]
            total = counts["perfect"] + counts["good"]
            return (
                counts["perfect"] / total,
                offset == self.baseline_offset_ms,
                -abs(offset - self.baseline_offset_ms),
            )

        self.selected_offset_ms = max(self.offsets, key=score)
        self.finished = True
        return {
            "offset_ms": self.selected_offset_ms,
            "phase": "complete",
            "save": self.selected_offset_ms != self.baseline_offset_ms,
            "reason": "comparison",
        }

    def finish(self):
        self.finished = True
        return self.selected_offset_ms if self.stage == len(self.offsets) - 1 else self.baseline_offset_ms


def classify_grade(text, confidence):
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").upper()
    normalized = re.sub(r"[^A-Z]", "", normalized)
    if confidence < 0.65 or not normalized:
        return None

    aliases = {
        "perfect": ("PERFECT", "PERFECTO"),
        "good": ("GOOD", "BUENO", "BIEN"),
    }
    for grade, labels in aliases.items():
        if normalized in labels:
            return grade
        if max(SequenceMatcher(None, normalized, label).ratio() for label in labels) >= 0.78:
            return grade
    return None


class VisualGradeReader:
    def __init__(self):
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR

        # one thread: the default lets onnxruntime spin a pool on every core, which used about 20 cores and starved the game
        self.ocr = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        self.ocr(np.zeros((64, 192), dtype=np.uint8), use_det=False, use_cls=False)
        self.last_combo = None

    def reset(self):
        self.last_combo = None

    def _recognize(self, image):
        result, _ = self.ocr(image, use_det=False, use_cls=False)
        if not result or len(result) != 1:
            return None, 0.0
        text, confidence = result[0]
        return str(text), float(confidence)

    def observe(self, frame, grade_region, combo_region):
        combo_crop = frame[combo_region[1]:combo_region[3], combo_region[0]:combo_region[2]]
        if combo_crop.size == 0:
            return None
        combo_text, combo_confidence = self._recognize(combo_crop)
        if combo_text is None or combo_confidence < 0.8:
            return None
        digits = re.findall(r"\d+", combo_text)
        if len(digits) != 1:
            return None
        combo = int(digits[0])

        previous_combo = self.last_combo
        self.last_combo = combo
        if previous_combo is None or combo != previous_combo + 1:
            return None

        grade_crop = frame[grade_region[1]:grade_region[3], grade_region[0]:grade_region[2]]
        if grade_crop.size == 0:
            return None
        grade_text, grade_confidence = self._recognize(grade_crop)
        if grade_text is None:
            return None
        return classify_grade(grade_text, grade_confidence)
