import re
import unicodedata


def is_gesto_prompt(results, minimum_confidence=0.8):
    labels = []
    for item in results or ():
        if len(item) < 3:
            continue
        text, confidence = item[1], item[2]
        if float(confidence) < minimum_confidence:
            continue
        normalized = unicodedata.normalize("NFKD", str(text))
        normalized = normalized.encode("ascii", "ignore").decode("ascii").upper()
        labels.append(re.sub(r"[^A-Z0-9]", "", normalized))

    has_gesto = any("GESTO" in label for label in labels)
    has_b = any(label == "B" or label.startswith("BGESTO") for label in labels)
    return has_b and has_gesto


class EmotePromptReader:
    def __init__(self, ocr, rearm_delay=0.5):
        if rearm_delay < 0:
            raise ValueError("rearm_delay must not be negative")
        self.ocr = ocr
        self.rearm_delay = rearm_delay
        self.last_seen = None

    def reset(self):
        self.last_seen = None

    def observe(self, frame, region, now):
        left, top, right, bottom = region
        if (
            left < 0
            or top < 0
            or right > frame.shape[1]
            or bottom > frame.shape[0]
            or left >= right
            or top >= bottom
        ):
            raise ValueError("Emote prompt region is outside the captured frame")
        crop = frame[top:bottom, left:right]

        result, _ = self.ocr(crop)
        if is_gesto_prompt(result):
            first_sighting = self.last_seen is None
            self.last_seen = now
            return first_sighting

        if self.last_seen is not None and now - self.last_seen >= self.rearm_delay:
            self.last_seen = None
        return False
