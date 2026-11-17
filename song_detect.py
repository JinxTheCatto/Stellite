# Reads the song setlist and the part off Fortnite Festival's ready screen ("¡PREPÁRATE!" / "GET READY!")
# Everything is laid out for 1920x1080, other 16:9 sizes get scaled to it first

import re
import unicodedata
from difflib import SequenceMatcher

import cv2
import numpy as np

HEADER = (780, 28, 1140, 84)
PART = (100, 908, 290, 952)
PART_ROW = (56, 896, 372, 962) # the whole part line, searched for text when the fixed spot above reads nothing useful
# while a song plays the bottom left of the screen names it: artist on one line, title under it, and the score line names the part
HUD_ARTIST = (26, 721, 326, 748)
HUD_TITLE = (26, 746, 326, 777)
HUD_SCORE = (24, 1008, 236, 1042)
HUD_TIME = (270, 800, 340, 828) # time left in the song ("-2:41"), under the song name and its progress bar while it plays
DIFFICULTY = (100, 962, 370, 1002)
# setlist cards: 1 2 on top, 3 4 below
SLOTS = ((565, 97), (960, 97), (565, 185), (960, 185))
TITLE_OFFSET = (97, 20, 297, 46)
ARTIST_OFFSET = (97, 44, 297, 68)

HEADER_WORDS = ("PREPARATE", "GETREADY", "READY")
EXPERT_WORDS = ("EXTREMO", "EXPERT", "EXPERTO")
# checked in order, the part name is often cut off on the left while it animates in
PART_WORDS = (
    ("drums", ("BATERIA", "ATERIA", "DRUMS", "RUMS")),
    ("bass", ("BAJO", "BASS")),
    ("vocals", ("VOZ", "VOCALES", "VOCALS", "OCALS")),
    # "INSTRUMENTO PRINCIPAL" does not fit its box, so depending on how far it has scrolled only a piece of it shows
    ("lead", ("PRINCIP", "RINCIPAL", "INCIPAL", "INSTRUM", "STRUMENTO", "LEAD", "GUITAR", "GUITARRA")),
)

def fold(text):
    decomposed = unicodedata.normalize("NFKD", str(text).strip().lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))

def letters(text):
    return re.sub(r"[^A-Z]", "", fold(text).upper())

def parse_part(text):
    # returns (instrument, is_pro), instrument is None when it cant tell
    upper = letters(text)
    is_pro = bool(re.search(r"\bPRO\b", fold(text).upper())) or upper.endswith("PRO")
    for instrument, words in PART_WORDS:
        if any(word in upper for word in words):
            return instrument, is_pro
    return None, is_pro

def is_expert(text):
    upper = letters(text)
    return any(word in upper for word in EXPERT_WORDS)

def parse_time_left(text):
    # seconds left from the song timer text, None when it does not read as a time. The slanted font often loses its colon
    # or turns a 1 into a t ("-228", "-t:51"), the digits themselves read right
    digits = []
    for character in str(text).strip():
        if character.isdigit():
            digits.append(character)
        elif character in "tlI|i!":
            digits.append("1")
        elif character in "Oo":
            digits.append("0")
        elif character not in "-\u2013\u2014\u2212:.;,' ":
            return None
    if len(digits) not in (3, 4):
        return None # "-:18" lost its minute, there is no telling which one
    minutes, seconds = int("".join(digits[:-2])), int("".join(digits[-2:]))
    return minutes * 60 + seconds if seconds <= 59 else None

def is_ready_screen(text):
    upper = letters(text)
    return any(word in upper for word in HEADER_WORDS)

def match_song(songs, title, artist, minimum=0.78):
    title = fold(title).rstrip(". …")
    artist = fold(artist)
    if len(title) < 2:
        return None
    best, best_score = None, 0.0
    for song in songs:
        name = fold(song["name"])
        song_title, _, song_artist = name.rpartition(" by ")
        if not song_title:
            song_title, song_artist = name, ""
        # long titles get cut off on the card, so compare against the same length
        title_score = SequenceMatcher(None, title, song_title[:max(len(title), 1) + 2]).ratio()
        artist_score = SequenceMatcher(None, artist, song_artist).ratio() if artist and song_artist else None
        # a title too long for its box scrolls, so what was read can be any piece of it
        if len(title) >= 6 and len(song_title) > len(title) and (len(title) >= 12 or (artist_score or 0) >= 0.6):
            piece = SequenceMatcher(None, title, song_title).find_longest_match(0, len(title), 0, len(song_title))
            title_score = max(title_score, 0.95 * piece.size / len(title))
        if artist_score is not None:
            score = 0.7 * title_score + 0.3 * artist_score
        else:
            score = title_score
        if score > best_score:
            best, best_score = song, score
    return best if best_score >= minimum else None

def to_1080(image):
    # scale to 1080 tall and return how far the centered layout is shifted sideways
    height, width = image.shape[:2]
    if height != 1080:
        image = cv2.resize(image, (round(width * 1080 / height), 1080), interpolation=cv2.INTER_AREA)
    return image, (image.shape[1] - 1920) // 2

class ReadyScreenReader:
    def __init__(self, ocr=None):
        if ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            # one thread: the default spins a pool on every core even for one small read per second
            ocr = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        self.ocr = ocr

    def text(self, image, box, shift=0):
        left, top, right, bottom = box
        crop = image[top:bottom, left + shift:right + shift]
        if crop.size == 0:
            return ""
        crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        result, _ = self.ocr(crop, use_det=False, use_cls=False)
        if not result:
            return ""
        text, confidence = result[0]
        return str(text) if float(confidence) >= 0.5 else ""

    def header_box(self, width, height):
        # where the header is on a real screen, so only that strip has to be grabbed every check
        scale = height / 1080
        shift = (width / scale - 1920) / 2
        left, top, right, bottom = HEADER
        return (round((left + shift) * scale), round(top * scale), round((right + shift) * scale), round(bottom * scale))

    def header_visible(self, header_bgr):
        header = np.ascontiguousarray(header_bgr)
        height = header.shape[0]
        if height == 0:
            return False
        scale = (HEADER[3] - HEADER[1]) / height
        if scale != 1:
            header = cv2.resize(header, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        return is_ready_screen(self.text(header, (0, 0, header.shape[1], header.shape[0])))

    def time_left_box(self, width, height):
        # where the song timer is on a real screen, so only that bit has to be grabbed
        scale = height / 1080
        left, top, right, bottom = HUD_TIME
        return (round(left * scale), round(top * scale), round(right * scale), round(bottom * scale))

    def time_left(self, timer_bgr):
        # seconds left in the song as the game shows it under the song name, from a picture of just that timer.
        # The game counts down from the song length and rounds up, so song position = length - this, give or take a second
        timer = np.ascontiguousarray(timer_bgr)
        if timer.shape[0] == 0 or timer.shape[1] == 0:
            return None
        scale = 3 * (HUD_TIME[3] - HUD_TIME[1]) / timer.shape[0]
        timer = cv2.resize(timer, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        result, _ = self.ocr(timer, use_det=False, use_cls=False)
        if not result:
            return None
        text, confidence = result[0]
        return parse_time_left(text) if float(confidence) >= 0.5 else None

    def read_playing(self, screenshot_bgr, songs):
        # the song named at the bottom left while it plays. the score line under it reads like "PUNTAJE DE VOZ" and gives the part
        image, _ = to_1080(np.ascontiguousarray(screenshot_bgr))
        title = self.text(image, HUD_TITLE)
        artist = self.text(image, HUD_ARTIST)
        song = match_song(songs, title, artist) if title else None
        part_text = self.text(image, HUD_SCORE)
        instrument, is_pro = parse_part(part_text)
        score_line = letters(part_text)
        return {
            "songs": [song] if song is not None else [],
            "instrument": instrument,
            "pro": is_pro,
            "expert": None, # not shown there
            "part_text": part_text,
            "unmatched": [(title, artist)] if title and song is None else [],
            "in_song": "PUNT" in score_line or "SCORE" in score_line, # the score line is only there while a song plays
        }

    def words(self, image, box):
        # every piece of text found inside the box, slower than text() because it has to find the text first
        left, top, right, bottom = box
        crop = image[top:bottom, left:right]
        if crop.size == 0:
            return ""
        crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        result, _ = self.ocr(crop)
        return " ".join(str(item[1]) for item in result or () if len(item) >= 3 and float(item[2]) >= 0.5)

    def read(self, screenshot_bgr, songs, force=False):
        # returns None when this isnt the ready screen, unless forced to read the song cards anyway
        image, shift = to_1080(np.ascontiguousarray(screenshot_bgr))
        if not is_ready_screen(self.text(image, HEADER, shift)) and not force:
            return None
        setlist = []
        unmatched = [] # (title, artist) as read, for the song cards that fit nothing in the list
        for slot_left, slot_top in SLOTS:
            title_box = (slot_left + TITLE_OFFSET[0], slot_top + TITLE_OFFSET[1], slot_left + TITLE_OFFSET[2], slot_top + TITLE_OFFSET[3])
            title = self.text(image, title_box, shift)
            if not title:
                continue
            artist_box = (slot_left + ARTIST_OFFSET[0], slot_top + ARTIST_OFFSET[1], slot_left + ARTIST_OFFSET[2], slot_top + ARTIST_OFFSET[3])
            artist = self.text(image, artist_box, shift)
            song = match_song(songs, title, artist)
            if song is not None:
                setlist.append(song)
            else:
                unmatched.append((title, artist))
        part_text = self.text(image, PART)
        instrument, is_pro = parse_part(part_text)
        if instrument is None:
            # the name can sit elsewhere on the line or be cut differently, so look over the whole line
            part_text = self.words(image, PART_ROW) or part_text
            instrument, is_pro = parse_part(part_text)
        return {
            "songs": setlist,
            "instrument": instrument,
            "pro": is_pro,
            "expert": is_expert(self.text(image, DIFFICULTY)),
            "part_text": part_text,
            "unmatched": unmatched,
        }
