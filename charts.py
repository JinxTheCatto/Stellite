# Song charts for Stellite
# Charts and overdrive paths are read straight from the CHOpt path images on fnfpaths (https://fnfpaths.github.io)
# Path image reading is based on Festival OD Coach by Aknownthreat, made for the Stellite project (GPL-3.0)
# https://github.com/Aknownthreat/-fortnite-festival-overdrive-timer

import os
import re
import sys
import json
import math
import time
import bisect
import copy
import threading
import unicodedata
import urllib.parse
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import msvcrt
import cv2
import numpy as np
from colorama import Fore, Style

SONGS_URL = "https://fnfpaths.github.io/fnfp.js"
PATHS_URL = "https://fnfpaths.github.io/paths/"
SPARK_URL = "https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/spark-tracks"
SONGS_FILE = os.path.join("data", "songs.json")
LENGTHS_FILE = os.path.join("data", "song_lengths.json")
CHARTS_FOLDER = os.path.join("data", "charts")
LEARNED_CHARTS_FILE = os.path.join("data", "learned_charts.json")
SONGS_MAX_AGE = 12 * 60 * 60 # redownload the song list twice a day

# fnfp.js field prefix -> instrument. the site names them weird, m is normal bass and b is pro bass
# pro lead (g) and pro bass (b) are left out on purpose
INSTRUMENTS = {"d": "drums", "l": "lead", "m": "bass", "v": "vocals"}
INSTRUMENT_NAMES = {"drums": "Drums", "lead": "Lead", "bass": "Bass", "vocals": "Vocals"}

SONG_RE = re.compile(r'\{\s*value\s*:\s*"([^"]+)"\s*,\s*data\s*:\s*\{(.*?)\}', re.DOTALL)
STEP_RE = re.compile(r"^\s*(\d+)(?:\(\+(\d+)\))?(?:/(.+))?\s*$") # path steps like 2(+1)/3rd RY
IMAGE_NAME_RE = re.compile(r'^[\w.\-]+\.png$')

# CHOpt image layout, from CHOpt src/image.cpp (fnfpaths' build draws rows 154px apart, first box at y=218)
BEAT_WIDTH = 60
LEFT_MARGIN = 31
MEASURE_HEIGHT = 61
FIRST_ROW_Y = 218
ROW_PITCH = 154
LANE_GAP = 15
MAX_BEATS_PER_LINE = 16
TEMPO_GREY = 160
TEMPO_BAND = (-46, -28) # tempo text sits above each box
GRIDS = (1, 2, 3, 4, 6, 8, 12, 16, 24) # note spacings to snap to, in parts of a beat

# CHOpt's 13px font, digits as drawn in the tempo markers
DIGIT_ROWS = {
    "0": (".###.", "##.##", "#...#", "#...#", "#...#", "#...#", "##.##", ".###."),
    "1": (".##..", "#.#..", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "2": (".###.", "#...#", "....#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": (".###.", "#...#", "....#", ".###.", "....#", "....#", "#...#", ".###."),
    "4": ("....#.", "...##.", "..#.#.", ".#..#.", "#...#.", "######", "....#.", "....#."),
    "5": ("#####", "#....", "#....", "####.", "....#", "....#", "....#", "####."),
    "6": ("..###", ".#...", "#....", "####.", "#...#", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "...#.", "..#..", "..#..", "..#..", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", "#...#", ".####", "....#", "...#.", "###.."),
}

# Black outlines of the note sprites. circles for normal notes, stars for overdrive phrase notes
CIRCLE_ROWS = (
    "...#####...",
    "..#.....#..",
    ".#.......#.",
    "#.........#",
    "#.........#",
    "#.........#",
    "#.........#",
    "#.........#",
    ".#.......#.",
    "..#.....#..",
    "...#####...",
)
STAR_ROWS = (
    ".....#.....",
    ".....#.....",
    "....#.#....",
    "....#.#....",
    "#####.#####",
    ".#.......#.",
    "..#.....#..",
    "...#...#...",
    "...#.#.#...",
    "..#.#.#.#..",
    "..##...##..",
    "..#.....#..",
)

def pattern(rows):
    return np.array([[c == "#" for c in row] for row in rows], dtype=np.float32)

DIGITS = {digit: pattern(rows) for digit, rows in DIGIT_ROWS.items()}
CIRCLE = pattern(CIRCLE_ROWS)
STAR = pattern(STAR_ROWS)
# notes packed tightly are drawn one over the other: the later one covers the right side of the one before, the left side always shows
CIRCLE_LEFT = CIRCLE[:, :6].copy()

def http_get(url, timeout = 60):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()

# Song list

def field(block, name):
    match = re.search(rf'\b{name}\s*:\s*"([^"]*)"', block)
    return match.group(1).replace("'", "").strip() if match else ""

def download_songs():
    js = http_get(SONGS_URL, 90).decode("utf-8", errors="replace")
    songs = []
    seen = set()
    for match in SONG_RE.finditer(js):
        name = match.group(1).strip()
        block = match.group(2)
        if name.lower() in seen:
            continue
        paths = {}
        for prefix, instrument in INSTRUMENTS.items():
            path = field(block, f"{prefix}path")
            image = field(block, f"{prefix}_image")
            if path and IMAGE_NAME_RE.match(image):
                paths[instrument] = {"path": path, "image": image}
        if not paths:
            continue
        seen.add(name.lower())
        songs.append({"name": name, "shortname": field(block, "shortname"), "paths": paths})
    songs.sort(key=lambda song: song["name"].lower())
    return songs

def download_song_lengths():
    # epic's track list has every song's length, the timer counts down from it like the one in game
    tracks = json.loads(http_get(SPARK_URL, 90).decode("utf-8", errors="replace"))
    lengths = {}
    for key, value in tracks.items():
        track = value.get("track") if isinstance(value, dict) else None
        if not isinstance(track, dict) or not isinstance(track.get("dn"), (int, float)) or track["dn"] <= 0:
            continue
        title = str(track.get("tt") or "").strip().lower()
        artist = str(track.get("an") or "").strip().lower()
        lengths[str(track.get("sn") or key).strip().lower()] = track["dn"]
        if title and artist:
            lengths[f"{title} by {artist}"] = track["dn"]
        if title:
            lengths.setdefault(title, track["dn"])
    return lengths

def load_saved(path, download, name):
    cached = None
    try:
        with open(path, "r", encoding="utf-8") as file:
            cached = json.load(file)
        if time.time() - os.path.getmtime(path) < SONGS_MAX_AGE:
            return cached
    except Exception:
        pass

    try:
        print(Fore.CYAN + f"Downloading {name}..." + Fore.RESET)
        data = download()
        if data:
            os.makedirs("data", exist_ok=True)
            with open(path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
            return data
        print(Fore.RED + f"Got nothing back for {name}" + Fore.RESET)
    except Exception as e:
        print(Fore.RED + f"Could not download {name}: {str(e)}" + Fore.RESET)
    if cached:
        print(Fore.YELLOW + "Using the saved copy instead" + Fore.RESET)
    return cached

def load_songs():
    return load_saved(SONGS_FILE, download_songs, "the song list from fnfpaths") or []

def load_song_lengths():
    return load_saved(LENGTHS_FILE, download_song_lengths, "song lengths from epic") or {}

def song_length(song, lengths):
    name = song["name"].strip().lower()
    for key in (name, str(song.get("shortname") or "").strip().lower(), name.split(" by ", 1)[0].strip()):
        if key and key in lengths:
            return float(lengths[key])
    return None

# Path image reading

def find_rows(image):
    height = image.shape[0]
    dark = image.max(axis=2) < 100 # black lines, also under the see through overlays
    rows = []
    beat = 0.0
    # image height = FIRST_ROW_Y + ROW_PITCH * row count
    for index in range((height - FIRST_ROW_Y) // ROW_PITCH):
        y = FIRST_ROW_Y + ROW_PITCH * index
        box = dark[y : y + MEASURE_HEIGHT + 1, LEFT_MARGIN:]
        full = np.flatnonzero(box.mean(axis=0) >= 0.6) # measure lines + right border
        length = full[-1] / BEAT_WIDTH if full.size else 0.0
        if length <= 0:
            length = float(MAX_BEATS_PER_LINE)
        length = round(length * 24) / 24 # x is cut to a whole pixel, rows end on a 1/24 beat grid
        rows.append((y, beat, beat + length))
        beat += length
    if not rows:
        raise ValueError("Could not find any chart rows in the path image")
    return rows

def read_tempos(image, rows):
    tempos = []
    for y, start, end in rows:
        y0, y1 = y + TEMPO_BAND[0], y + TEMPO_BAND[1]
        if y0 < 0:
            continue
        mask = np.all(image[y0:y1] == TEMPO_GREY, axis=2).astype(np.float32)
        # quarter note glyph: 12px stem at x+4 starting 2px into the band, head at x..x+1
        stems = np.flatnonzero(mask[2:14].min(axis=0) > 0)
        notes = [int(x) - 4 for x in stems if x >= 4 and mask[12:14, x - 4 : x - 2].all()]
        if not notes:
            continue

        digits = []
        padded = np.pad(mask, 1)
        for digit, template in DIGITS.items():
            # exact match with a blank border so a digit cant match inside another one
            difference = cv2.matchTemplate(padded, np.pad(template, 1), cv2.TM_SQDIFF)
            for x in np.nonzero(difference < 0.5)[1]:
                digits.append((int(x), digit))
        digits.sort()

        for index, note_x in enumerate(notes):
            limit = notes[index + 1] if index + 1 < len(notes) else note_x + 40
            text = "".join(d for x, d in digits if note_x + 10 <= x < min(limit, note_x + 40))
            if 2 <= len(text) <= 3 and 20 <= int(text) <= 600:
                tempos.append((start + (note_x - LEFT_MARGIN) / BEAT_WIDTH, float(text)))
    tempos.sort()
    return tempos

def blue_ranges(image, rows):
    b = image[..., 0].astype(np.int16)
    g = image[..., 1].astype(np.int16)
    r = image[..., 2].astype(np.int16)
    # activation blue at 1/3 opacity: (170,170,255) on white, (113,170,198) over green
    blue = (b >= 180) & (b - r >= 50) & (b - g >= 20) & (r >= 60)

    found = []
    for y, start, end in rows:
        x1 = LEFT_MARGIN + int(round((end - start) * BEAT_WIDTH))
        column = blue[y + 1 : y + MEASURE_HEIGHT - 1, LEFT_MARGIN : x1 + 1].mean(axis=0)
        on = np.flatnonzero(column >= 0.5)
        if on.size == 0:
            continue
        # split into runs, bridging the small gaps from black measure lines under the overlay
        breaks = np.flatnonzero(np.diff(on) > 4)
        starts = np.concatenate(([on[0]], on[breaks + 1]))
        ends = np.concatenate((on[breaks], [on[-1]]))
        for sx, ex in zip(starts, ends):
            if ex - sx < 4:
                continue
            found.append((snap_beat(start, LEFT_MARGIN + sx), min(end, start + (ex + 1) / BEAT_WIDTH)))

    merged = []
    for start, end in sorted(found):
        if merged and start <= merged[-1][1] + 0.1: # keeps going on the next row
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged if end - start >= 0.25]

def snap_beat(row_start, x):
    # CHOpt cuts x down to a whole pixel, so the real beat is somewhere inside this pixel. snap it onto the closest musical grid
    low = (x - LEFT_MARGIN - 0.01) / BEAT_WIDTH
    high = (x - LEFT_MARGIN + 1.01) / BEAT_WIDTH
    for grid in GRIDS:
        snapped = math.ceil(low * grid) / grid
        if snapped <= high:
            return row_start + snapped
    return row_start + (x - LEFT_MARGIN + 0.5) / BEAT_WIDTH

def find_notes(image, rows):
    dark = (image.max(axis=2) < 100).astype(np.float32)
    notes = []
    for row_index, (y, start, end) in enumerate(rows):
        x_end = LEFT_MARGIN + int(round((end - start) * BEAT_WIDTH))
        for lane in range(5):
            line = y + LANE_GAP * lane
            band = dark[line - 7 : line + 8, LEFT_MARGIN - 7 : x_end + 8]
            # how much of each outline is black, with the sprite centered on the lane line
            circles = cv2.matchTemplate(band[2:13], CIRCLE, cv2.TM_CCORR)[0] / CIRCLE.sum()
            lefts = cv2.matchTemplate(band[2:13], CIRCLE_LEFT, cv2.TM_CCORR)[0] / CIRCLE_LEFT.sum()
            stars = cv2.matchTemplate(band[1:13], STAR, cv2.TM_CCORR)[0] / STAR.sum()
            circle_scores = np.zeros(band.shape[1], dtype=np.float32)
            left_scores = np.zeros(band.shape[1], dtype=np.float32)
            star_scores = np.zeros(band.shape[1], dtype=np.float32)
            circle_scores[5 : 5 + circles.size] = circles
            left_scores[5 : 5 + lefts.size] = lefts
            star_scores[5 : 5 + stars.size] = stars
            score = np.maximum(circle_scores, star_scores)
            positions = []
            last_x = -100
            for x in np.flatnonzero(score >= 0.85):
                if score[x] < score[max(0, x - 3) : x + 4].max() or x - last_x < 4:
                    continue
                last_x = x
                positions.append(int(x))
            # In a very fast run on one key the notes touch, and each one is drawn over the right side of the one before it.
            # Such a note has its left side whole and the note that covers it right next to it. Going from the right, so a
            # note found this way can stand in for the one that covers the note before it.
            found = set(positions)
            covered = (score < 0.85) & (circle_scores >= 0.6) & (left_scores >= 0.93)
            for x in np.flatnonzero(covered)[::-1]:
                if left_scores[x] < left_scores[max(0, x - 2) : x + 3].max():
                    continue
                if any(x + gap in found for gap in range(-4, 5)) or not any(x + gap in found for gap in range(5, 11)):
                    continue
                found.add(int(x))
            for position in sorted(found):
                overdrive = star_scores[position] > circle_scores[position]
                note_x = position + LEFT_MARGIN - 7
                notes.append((snap_beat(start, note_x), lane, row_index, note_x, overdrive))
    return notes

def sustain_end(image, rows, row_index, x, lane):
    def bar(row, column):
        line = rows[row][0] + LANE_GAP * lane
        inside = (image[line - 2, column].astype(np.int16), image[line + 2, column].astype(np.int16))
        outside = (image[line - 6, column].astype(np.int16), image[line + 6, column].astype(np.int16))
        # sustains are a 7px tall colored bar on the lane line, so the middle is colored and unlike the pixels just outside it
        if any(int(pixel.max()) - int(pixel.min()) < 70 for pixel in inside):
            return False
        return sum(int(np.abs(a - b).sum()) for a, b in zip(inside, outside)) >= 120

    row = row_index
    column = x + 6 # right after the note sprite
    last = None
    while row < len(rows):
        y, start, end = rows[row]
        x_end = LEFT_MARGIN + int(round((end - start) * BEAT_WIDTH))
        gap = 0
        while column <= x_end:
            if bar(row, column):
                last = (row, column)
                gap = 0
            else:
                gap += 1
                if gap > 2:
                    break
            column += 1
        # long sustains carry on at the start of the next row
        if last is not None and last[0] == row and last[1] >= x_end - 1 and row + 1 < len(rows) and bar(row + 1, LEFT_MARGIN + 1):
            row += 1
            column = LEFT_MARGIN
            continue
        break

    if last is None or (last[0] == row_index and last[1] < x + 9):
        return None
    y, start, end = rows[last[0]]
    return start + (last[1] + 1 - LEFT_MARGIN) / BEAT_WIDTH

def tempo_seconds(tempos):
    beats, seconds, bpms = [], [], []
    total = 0.0
    for index, (beat, bpm) in enumerate(tempos):
        if index:
            total += (beat - beats[-1]) * 60.0 / bpms[-1]
        beats.append(beat)
        seconds.append(total)
        bpms.append(bpm)

    def to_seconds(beat):
        index = max(0, bisect.bisect_right(beats, beat) - 1)
        return seconds[index] + (beat - beats[index]) * 60.0 / bpms[index]
    return to_seconds

LIFT_SECONDS = 0.095 # the same single note again on a key sooner than this is hit by letting go of the first one

def find_lifts(placed):
    # placed is (seconds, lane, has a sustain, overdrive note) for every note. Returns the indexes of the lift notes.
    # When a single note repeats on its key very quickly the game joins the two into one tall note with an arrow on top:
    # press at its bottom, keep holding, let go at its top. The second note of such a pair is hit by the release.
    # It goes by time, not by note length. Seen in recordings: pairs 67, 78, 88 and 94 ms apart are joined, pairs
    # 96 and 100 ms apart (16ths at 156 and 150 bpm) are two ordinary notes, and letting go on those misses the second.
    # Overdrive notes are joined the same way (they show up white). Chords and sustains are left as ordinary presses,
    # and in a longer run the notes pair up two by two.
    together = {}
    for when, lane, sustain, overdrive in placed:
        together[round(when, 4)] = together.get(round(when, 4), 0) + 1
    lifts = set()
    for lane in range(5):
        pressed = None # time of the last plain note on this key that still gets a normal press
        for index in sorted((index for index, note in enumerate(placed) if note[1] == lane), key=lambda index: placed[index][0]):
            when, _, sustain, overdrive = placed[index]
            plain = together[round(when, 4)] == 1 and not sustain
            if plain and pressed is not None and 0 < when - pressed < LIFT_SECONDS:
                lifts.add(index)
                pressed = None # the note after a lift starts over with a press
            else:
                pressed = when if plain else None
    return lifts

def note_actions(chart, hold):
    # what the keys do for every note of the chart: (time, order, kind, lane). kind is press, hold, release or lift
    lift_times = [sorted(time for time, lane in chart.get("lift_notes", ()) if lane == key) for key in range(5)]
    def lift(time, lane):
        times = lift_times[lane]
        spot = bisect.bisect_left(times, time - 0.04)
        return spot < len(times) and times[spot] <= time + 0.04
    actions = []
    for lane in range(5):
        lane_notes = [note for note in chart["notes"] if note[1] == lane]
        index = 0
        while index < len(lane_notes):
            start, note_lane, length = lane_notes[index]
            following = lane_notes[index + 1] if index + 1 < len(lane_notes) else None
            if following is not None and lift(following[0], lane) and not lift(start, lane):
                # the next note on this key is hit by letting go: one press here, held, and released right on that note
                actions.append((start, 1, "hold", lane))
                actions.append((following[0], 0, "lift", lane))
                index += 2
                continue
            release = start + max(hold, length)
            if following is not None:
                # let go a bit before the next note in this lane so it counts as a new press
                release = min(release, following[0] - 0.01)
            kind = "hold" if length > hold and release > start + hold else "press"
            actions.append((start, 1, kind, lane))
            release = max(release, start + 0.005)
            actions.append((release, 0, "release", lane))
            index += 1
    return actions

def parse_chart(png):
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode the path image")
    rows = find_rows(image)
    tempos = read_tempos(image, rows)
    if not tempos:
        raise ValueError("Could not read the tempo markers in the path image")
    if tempos[0][0] > 1e-6:
        tempos.insert(0, (0.0, tempos[0][1]))
    to_seconds = tempo_seconds(tempos)

    placed = [] # beat, lane, beat its sustain ends on (None without one), overdrive note
    for beat, lane, row_index, x, overdrive in find_notes(image, rows):
        placed.append([beat, lane, sustain_end(image, rows, row_index, x, lane), overdrive])
    if not placed:
        raise ValueError("No notes found in the path image")
    # notes drawn so close together that their sprites touch read like a sustain running into the next one.
    # a real sustain is over before the next note on its key, and no sustain fits between two sprites that touch
    for lane in range(5):
        on_key = sorted((note for note in placed if note[1] == lane), key=lambda note: note[0])
        for note, following in zip(on_key, on_key[1:]):
            if note[2] is not None and (note[2] > following[0] + 1.5 / BEAT_WIDTH or following[0] - note[0] <= 12.5 / BEAT_WIDTH):
                note[2] = None
    lifts = find_lifts([(float(to_seconds(beat)), lane, end is not None, overdrive) for beat, lane, end, overdrive in placed])

    notes = []
    overdrive_notes = []
    lift_notes = []
    note_beats = set()
    for index, (beat, lane, end, overdrive) in enumerate(placed):
        start_time = float(to_seconds(beat))
        length = float(to_seconds(end)) - start_time if end is not None else 0.0
        notes.append((start_time, lane, max(0.0, length)))
        if overdrive:
            overdrive_notes.append((start_time, lane))
        if index in lifts:
            lift_notes.append((start_time, lane))
        note_beats.add(beat)
    notes.sort()
    note_beats = sorted(note_beats)

    # blue starts at the note before the first overdrive note, so overdrive has to be hit somewhere between those two notes
    overdrive = []
    for start, end in blue_ranges(image, rows):
        index = bisect.bisect_right(note_beats, start + 1.5 / BEAT_WIDTH)
        if index >= len(note_beats):
            continue
        window_start = float(to_seconds(start))
        window_end = float(to_seconds(note_beats[index]))
        overdrive.append(((window_start + window_end) / 2, window_start, window_end))

    return {
        "notes": notes,
        "overdrive_notes": overdrive_notes,
        "lift_notes": lift_notes,
        "overdrive": overdrive,
        "end": max(time + length for time, lane, length in notes),
        "tempos": tempos,
    }

def load_chart(song, instrument, lengths = None):
    image_name = song["paths"][instrument]["image"]
    if not IMAGE_NAME_RE.match(image_name):
        raise ValueError(f"Bad path image name {image_name}")
    # charts already read this session (for the note counts) are reused instead of downloaded again
    with parsed_lock:
        parsed = parsed_charts.get(image_name)
    if parsed is not None:
        return finish_chart(copy.deepcopy(parsed), song, instrument, lengths)
    cache = os.path.join(CHARTS_FOLDER, image_name)
    try:
        png = http_get(PATHS_URL + urllib.parse.quote(image_name))
        os.makedirs(CHARTS_FOLDER, exist_ok=True)
        with open(cache, "wb") as file:
            file.write(png)
    except Exception as e:
        if not os.path.isfile(cache):
            raise
        print(Fore.YELLOW + f"Could not download the path image ({str(e)}), using the saved one" + Fore.RESET)
        with open(cache, "rb") as file:
            png = file.read()
    chart = parse_chart(png)
    with parsed_lock:
        parsed_charts[image_name] = copy.deepcopy(chart)
    return finish_chart(chart, song, instrument, lengths)

def finish_chart(chart, song, instrument, lengths):
    chart["name"] = song["name"]
    chart["instrument"] = instrument
    chart["path"] = song["paths"][instrument]["path"]
    chart["length"] = song_length(song, lengths or {})

    # the path text says which note to activate on, only trust it if it has as many steps as the image has activations
    steps = [step.strip() for step in chart["path"].split(",") if step.strip()]
    chart["overdrive_labels"] = []
    for index in range(len(chart["overdrive"])):
        if len(steps) != len(chart["overdrive"]):
            chart["overdrive_labels"].append(f"activation {index + 1}")
            continue
        match = STEP_RE.match(steps[index])
        chart["overdrive_labels"].append((match.group(3) or "NN").strip() if match else steps[index])
    return chart

parsed_charts = {}
parsed_lock = threading.Lock()

def note_counts(song, instruments):
    # reads every instrument's chart at the same time so the picker only waits for the slowest one
    def count(instrument):
        learned = load_learned_chart(song, instrument)
        if learned is not None:
            return instrument, len(learned["notes"])
        try:
            return instrument, len(load_chart(song, instrument)["notes"])
        except Exception:
            return instrument, None
    with ThreadPoolExecutor(max_workers=len(instruments) or 1) as pool:
        return dict(pool.map(count, instruments))

def learned_chart_key(song, instrument):
    return f"{song.get('shortname') or song['name'].strip().lower()}:{instrument}"

def normalize_learned_notes(notes):
    normalized = []
    for note in notes:
        if not isinstance(note, (list, tuple)) or len(note) != 3:
            raise ValueError("each note must have a time, lane, and sustain length")
        start, lane_value, length = float(note[0]), float(note[1]), float(note[2])
        if (
            not math.isfinite(start) or not math.isfinite(lane_value) or not math.isfinite(length)
            or start < 0 or length < 0 or not lane_value.is_integer()
        ):
            raise ValueError("learned note values are out of range")
        lane = int(lane_value)
        if lane not in range(5):
            raise ValueError("learned note lane is out of range")
        normalized.append((start, lane, length))
    return normalized

def restore_source_drums_sustains(learned_notes, source_chart):
    normalized = normalize_learned_notes(learned_notes)
    if source_chart.get("instrument") != "drums":
        return normalized

    restored = list(normalized)
    for lane in range(5):
        source_lane = sorted(
            (note for note in source_chart["notes"] if note[1] == lane),
            key=lambda note: note[0],
        )
        learned_lane = sorted(
            ((index, note) for index, note in enumerate(normalized) if note[1] == lane),
            key=lambda item: item[1][0],
        )
        source_holds = [note for note in source_lane if note[2] > 0.05]
        if not source_holds or not learned_lane:
            continue

        source_span = source_lane[-1][0] - source_lane[0][0]
        learned_span = learned_lane[-1][1][0] - learned_lane[0][1][0]
        spacing = learned_span / max(1, len(learned_lane) - 1)
        used = set()
        for hold in source_holds:
            position = (hold[0] - source_lane[0][0]) / source_span if source_span else 0.0
            expected_time = learned_lane[0][1][0] + position * learned_span
            available = [
                (index, note) for index, note in learned_lane
                if index not in used
            ]
            if not available:
                break
            index, note = min(available, key=lambda item: abs(item[1][0] - expected_time))
            if abs(note[0] - expected_time) <= max(0.5, spacing * 2):
                restored[index] = (note[0], note[1], hold[2])
                used.add(index)
    return restored

def learned_chart_quality(learned_chart, source_chart):
    for lane in range(5):
        source_notes = [note for note in source_chart["notes"] if note[1] == lane]
        learned_notes = [note for note in learned_chart["notes"] if note[1] == lane]
        source_count = len(source_notes)
        learned_count = len(learned_notes)
        if source_count == 0:
            if learned_count:
                return f"lane {lane + 1} has {learned_count} learned notes but none in the source chart"
        elif learned_count < source_count * 0.9 or learned_count > source_count * 1.5:
            return f"lane {lane + 1} has {learned_count} learned notes versus {source_count} in the source chart"

        source_holds = [note[2] for note in source_notes if note[2] > 0.05]
        learned_holds = [note[2] for note in learned_notes if note[2] > 0.05]
        if source_chart.get("instrument") == "drums" and len(learned_holds) != len(source_holds):
            return f"lane {lane + 1} has {len(learned_holds)} learned sustains versus {len(source_holds)} in the source chart"
        if learned_holds and not source_holds:
            return f"lane {lane + 1} has learned sustains but none in the source chart"
        if len(learned_holds) > math.ceil(len(source_holds) * 1.5):
            return f"lane {lane + 1} has {len(learned_holds)} learned sustains versus {len(source_holds)} in the source chart"
        if source_holds and learned_holds and max(learned_holds) > max(source_holds) * 2 + 0.5:
            return f"lane {lane + 1} has a learned sustain much longer than the source chart"
    return None

def load_learned_chart(song, instrument):
    try:
        with open(LEARNED_CHARTS_FILE, "r", encoding="utf-8") as file:
            learned = json.load(file)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as e:
        print(Fore.YELLOW + f"Could not read learned charts: {str(e)}" + Fore.RESET)
        return None

    entry = learned.get(learned_chart_key(song, instrument)) if isinstance(learned, dict) else None
    if not isinstance(entry, dict) or not isinstance(entry.get("notes"), list):
        return None
    try:
        notes = normalize_learned_notes(entry["notes"])
    except (TypeError, ValueError, IndexError):
        print(Fore.YELLOW + f"Learned chart for {song['name']} is invalid; using the online chart" + Fore.RESET)
        return None
    if not notes:
        return None

    notes.sort()
    return {
        "name": song["name"],
        "shortname": song.get("shortname"),
        "instrument": instrument,
        "notes": notes,
        "overdrive_notes": [],
        "overdrive": [],
        "overdrive_labels": [],
        "end": max(start + length for start, lane, length in notes),
        "length": None,
        "path": "learned from screen",
        "learned": True,
    }

def save_learned_chart(song, instrument, notes, source_chart=None):
    normalized_notes = normalize_learned_notes(notes)
    key = learned_chart_key(song, instrument)
    try:
        with open(LEARNED_CHARTS_FILE, "r", encoding="utf-8") as file:
            learned = json.load(file)
        if not isinstance(learned, dict):
            raise ValueError("learned chart file must contain an object")
    except FileNotFoundError:
        learned = {}

    current = learned.get(key)
    if isinstance(current, dict) and isinstance(current.get("notes"), list):
        if source_chart is None and len(normalized_notes) < len(current["notes"]):
            return False
        if source_chart is not None:
            try:
                current_notes = normalize_learned_notes(current["notes"])
            except (TypeError, ValueError):
                current_notes = None
            if (
                current_notes is not None
                and len(normalized_notes) < len(current_notes)
                and learned_chart_quality({"notes": current_notes}, source_chart) is None
            ):
                return False

    learned[key] = {
        "name": song["name"],
        "shortname": song.get("shortname"),
        "instrument": instrument,
        "notes": [[round(start, 4), lane, round(length, 4)] for start, lane, length in normalized_notes],
    }
    os.makedirs(os.path.dirname(LEARNED_CHARTS_FILE), exist_ok=True)
    temporary = LEARNED_CHARTS_FILE + ".tmp"
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(learned, file, indent=2, ensure_ascii=False)
    os.replace(temporary, LEARNED_CHARTS_FILE)
    return True

def clock(seconds):
    seconds = max(0.0, seconds)
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"

# Song picker

def fold(text):
    # lowercase and strip accents so "get busy" finds "Gët Busy"
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))

def find_songs(songs, query):
    query = fold(query)
    if not query:
        return []
    exact = [song for song in songs if fold(song["name"]) == query]
    if exact:
        return exact
    starts = [song for song in songs if fold(song["name"]).startswith(query)]
    if starts:
        return starts
    return [song for song in songs if query in fold(song["name"])]

def common_prefix(names):
    if not names:
        return ""
    prefix = names[0]
    for name in names[1:]:
        while not name.lower().startswith(prefix.lower()):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix

def prompt_song(songs):
    # throw away anything typed into the console before the picker opened
    while msvcrt.kbhit():
        msvcrt.getwch()

    print(Fore.MAGENTA + Style.BRIGHT + "\nPick a song" + Style.RESET_ALL)
    print("Type to search, Tab autofills, Up/Down choose, Enter confirms, Esc skips (screen reading only)")
    print()

    buffer = ""
    selected = 0
    lines_used = 0

    def clear_block():
        nonlocal lines_used
        if lines_used > 0:
            sys.stdout.write(f"\033[{lines_used}A\033[J")
            lines_used = 0

    def redraw():
        nonlocal selected, lines_used
        clear_block()
        matches = find_songs(songs, buffer)[:10]
        if selected >= len(matches):
            selected = max(0, len(matches) - 1)
        hint = Fore.CYAN + f"  -> {matches[selected]['name']}" + Style.RESET_ALL if matches else ""
        print(Fore.WHITE + "Song: " + Style.RESET_ALL + buffer + hint)
        lines_used = 1
        if not buffer:
            print(Fore.YELLOW + "  (start typing)" + Style.RESET_ALL)
            lines_used += 1
        elif not matches:
            print(Fore.RED + "  no matches" + Style.RESET_ALL)
            lines_used += 1
        else:
            for index, song in enumerate(matches):
                if index == selected:
                    print(Fore.GREEN + Style.BRIGHT + f"  > {index + 1}. {song['name']}" + Style.RESET_ALL)
                else:
                    print(f"    {index + 1}. {song['name']}")
                lines_used += 1
        sys.stdout.flush()
        return matches

    matches = redraw()
    while True:
        key = msvcrt.getwch()
        if key in ("\r", "\n"):
            clear_block()
            if not buffer.strip():
                return None
            if matches:
                print(Fore.GREEN + f"Song: {matches[selected]['name']}" + Style.RESET_ALL)
                return matches[selected]
            print(Fore.RED + "No match, keep typing" + Style.RESET_ALL)
            matches = redraw()
        elif key == "\x1b":
            clear_block()
            return None
        elif key == "\t":
            if not matches:
                continue
            if len(matches) == 1:
                buffer = matches[0]["name"]
            else:
                prefix = common_prefix([match["name"] for match in matches])
                buffer = prefix if len(prefix) > len(buffer) else matches[selected]["name"]
            selected = 0
            matches = redraw()
        elif key in ("\x08", "\x7f"):
            buffer = buffer[:-1]
            selected = 0
            matches = redraw()
        elif key in ("\x00", "\xe0"):
            arrow = msvcrt.getwch()
            if matches and arrow == "H":
                selected = (selected - 1) % len(matches)
                matches = redraw()
            elif matches and arrow == "P":
                selected = (selected + 1) % len(matches)
                matches = redraw()
        elif key.isprintable():
            buffer += key
            selected = 0
            matches = redraw()

def prompt_instrument(song, default):
    available = [instrument for instrument in INSTRUMENT_NAMES if instrument in song["paths"]]
    if not available:
        print(Fore.RED + "No charts for this song" + Fore.RESET)
        return None
    if default not in available:
        default = available[0]
    print(Fore.CYAN + "Counting notes..." + Style.RESET_ALL, end="\r", flush=True)
    counts = note_counts(song, available)
    while msvcrt.kbhit(): # ignore keys pressed while counting
        msvcrt.getwch()
    def label(instrument):
        notes = counts.get(instrument)
        return INSTRUMENT_NAMES[instrument] + (f" ({notes:,} notes)" if notes is not None else "")
    print("Instrument: " + "  ".join(
        (Fore.GREEN + Style.BRIGHT if instrument == default else "") + f"[{index + 1}] {label(instrument)}" + Style.RESET_ALL
        for index, instrument in enumerate(available)
    ) + f"   (Enter = {INSTRUMENT_NAMES[default]}, Esc = skip)")
    while True:
        key = msvcrt.getwch()
        if key in ("\r", "\n"):
            return default
        if key == "\x1b":
            return None
        if key.isdigit() and 1 <= int(key) <= len(available):
            return available[int(key) - 1]

def prompt_queue_another(prompt="Queue another song? (Y/N)"):
    print(prompt)
    while True:
        key = msvcrt.getwch().lower()
        if key in ("y", "n"):
            return key == "y"

# Chart sync
# The game has no way to tell us where the song is, so we line the chart up with the notes the screen reader sees.
# Once locked, sightings can correct drift; a temporary detection gap must not discard the chart clock.

class ChartSync:
    fine_tune = True # false keeps the clock from the first sync, sightings then only check for wrong notes
    REALIGN_RANGE = 0.75 # how far off the clock can be and still be pulled back without leaving chart mode
    REALIGN_SIGHTINGS = 5 # notes seen that have to agree on the same shift
    REALIGN_WINDOW = 6.0 # only notes seen this recently get a vote
    REALIGN_TOLERANCE = 0.03
    MAX_DRIFT = 0.008 # CHOpt rounds tempos to whole bpm, and a busy pc can make the game itself fall behind
    START_SIGHTINGS = 4 # at the very start of the song this many notes that fit are enough to lock, so nobody has to press a key
    START_SPAN = 3.0 # how far into the chart's notes the first one seen may be for that
    # how well the notes seen have to fit before the clock locks. dense charts fit anything loosely, even another song
    LOCK_TOLERANCE = 0.04
    LOCK_SHARE = 0.75 # this share of the notes seen has to fit
    LOCK_SIGHTINGS_BLIND = 10 # notes needed when there is no hint about where in the song it is
    LOCK_FROM = None # how many of the notes seen may propose a spot, None is all of them
    LOST_SIGHTINGS = 10 # with at least this many notes seen in the last LOST_WINDOW seconds ...
    LOST_SHARE = 0.7 # ... and this share of them fitting nothing, the clock is lost: back to reading the screen
    LOST_WINDOW = 20.0
    HINT_AGE = 6.0 # the game's own song timer is only believed this long after it was read
    HINT_PATIENCE = 30 # notes seen without a spot the timer agrees with before the timer is doubted instead
    REALIGN_RECENT = 2.0 # a clock that is really off misses nearly every note, so most notes of the last seconds were seen
    REALIGN_SEEN_SHARE = 0.5
    REALIGN_UNDO = 10.0 # a jump straight back within this long means the first jump was wrong, and so is the speed it taught
    def __init__(self, chart, tolerance = 0.05):
        self.tolerance = tolerance
        self.end = chart["end"]
        # padded so the nearest note lookup never runs off either end
        self.lane_times = []
        for lane in range(5):
            times = sorted(time for time, note_lane, length in chart["notes"] if note_lane == lane)
            self.lane_times.append(np.array([-1e9] + times + [1e9]))
        self.note_times = np.array(sorted(set(time for time, lane, length in chart["notes"])))
        self.mutex = threading.RLock()
        self.version = 0
        self.active_since = 0.0
        self.position_hint = None # (when it was read, song position then, how far off it can be) from the game's song timer
        self.hint_bias = 0.0 # how far the timer turned out to be from the notes for this song
        self.timer_misses = 0 # times a spot taken from the timer fell apart right away, twice and the timer is left out
        self.reset()

    def reset(self, expect = "start"):
        with self.mutex:
            self.sightings = deque(maxlen=40)
            self.matches = deque(maxlen=48)
            self.last_matched = [None] * 5
            self.recent = deque(maxlen=24) # (when, lane) of the last notes seen while locked, they vote on where the song really is
            self.checks = deque(maxlen=400) # (when, how far the screen was from the chart) for notes that fit
            self.lost = False
            self.realigns = 0
            self.aligned = None # song time the clock was last lined up with notes seen on screen, a manual sync doesnt count
            self.history = [] # first few sightings since the last reset
            self.seen_since_hint = 0 # notes seen while waiting for a spot the game's timer agrees with
            self.tried = 0
            self.locked = False
            self.manual = False
            self.initial_press_lanes = set()
            self.model = (0.0, 0.0, 0.0) # offset, drift, reference
            self.before_realign = None # (when, shift, drift and alignment before it) of the last jump, to take it back
            self.locked_by = None # what settled the spot in the song: "start", "timer", "notes" or "key"
            self.locked_at = None
            # where the first note seen could be in the song (low, high, closest to), songs repeat a lot so this keeps it from locking onto the wrong chorus
            self.expect = [self.song_start()] if expect == "start" else (expect or [])
            self.version += 1

    def song_start(self):
        # None means take the earliest spot
        return (-1e9, self.note_times[0] + 20, None)

    def unlock(self, keep_sightings = False, expect = None):
        with self.mutex:
            sightings = list(self.sightings)[-12:] if keep_sightings else []
            self.reset(expect)
            self.sightings.extend(sightings)
            self.history = [seen for seen, lane in sightings]

    # wall clock = offset + song time + drift * (song time - reference)
    # drift is there because CHOpt rounds the tempo markers to whole bpm, so the chart slowly runs ahead or behind the song
    def wall_time(self, song_time):
        offset, drift, reference = self.model
        return offset + song_time + drift * (song_time - reference)

    def song_time(self, now):
        offset, drift, reference = self.model
        return (now - offset + drift * reference) / (1 + drift)

    def hint_position(self, now, position, margin=1.0):
        # Where the game's own song timer says the song is. Riffs repeat, so the notes alone often fit many spots:
        # the timer says which one, at the start and in the middle of a song alike
        with self.mutex:
            self.position_hint = (now, position, margin)

    def hinted_position(self, now):
        # song position by the game's timer, None when there is no fresh reading
        with self.mutex:
            hint = self.position_hint
            if hint is None or self.timer_misses >= 2 or abs(now - hint[0]) > self.HINT_AGE:
                return None
            return hint[1] + self.hint_bias + (now - hint[0])

    def start_at(self, now, song_time, press_lanes=()):
        with self.mutex:
            self.reset()
            self.model = (now - song_time, 0.0, 0.0)
            self.locked = True
            self.locked_by = "key"
            self.manual = True
            self.active_since = now
            self.initial_press_lanes = set(press_lanes)

    def start_now(self, now):
        # Manual sync with song time zero at now.
        self.start_at(now, 0.0)

    def resume(self, now):
        self.active_since = now

    def add_sighting(self, now, lane, playback_offset=0.0):
        with self.mutex:
            self.sightings.append((now, lane))
            if not self.locked:
                if self.position_hint is not None:
                    self.seen_since_hint += 1
                if len(self.history) < 12:
                    self.history.append(now)
                return
            times = self.lane_times[lane]
            # after a manual sync the clock is tied to the key press, so notes are expected on screen when they get played
            manual_offset = playback_offset if self.manual else 0.0
            guess = self.song_time(now - manual_offset)
            index = int(np.searchsorted(times, guess))
            nearest = times[index] if times[index] - guess < guess - times[index - 1] else times[index - 1]
            error = now - (self.wall_time(nearest) + manual_offset)
            self.recent.append((now, lane))
            if abs(error) > self.tolerance:
                expected_lanes = []
                for expected_lane, expected_times in enumerate(self.lane_times):
                    index = int(np.searchsorted(expected_times, guess))
                    expected = expected_times[index] if expected_times[index] - guess < guess - expected_times[index - 1] else expected_times[index - 1]
                    if abs(now - (self.wall_time(expected) + manual_offset)) <= self.tolerance:
                        expected_lanes.append(expected_lane)
                if self.fine_tune and not self.realign(now, manual_offset):
                    seen, astray = self.strays(now, manual_offset)
                    self.lost = seen >= self.LOST_SIGHTINGS and astray >= self.LOST_SHARE * seen
                return expected_lanes or None
            if self.last_matched[lane] == nearest:
                return
            self.last_matched[lane] = nearest
            self.checks.append((now, error))
            if not self.fine_tune:
                return
            # a note that fits can still be the neighbour of the right one, the vote over the last few notes knows better
            if self.realign(now, manual_offset):
                return
            self.matches.append((float(nearest), now - float(nearest)))
            self.manual = False
            self.fit()
            if self.aligned is None:
                self.aligned = float(nearest)

    def strays(self, now, manual_offset=0.0):
        # of the notes seen lately, how many fit nothing on the chart where the clock is now. returns (seen, astray)
        count = astray = 0
        for seen, lane in self.recent:
            if now - seen > self.LOST_WINDOW:
                continue
            count += 1
            times = self.lane_times[lane]
            guess = self.song_time(seen - manual_offset)
            index = int(np.searchsorted(times, guess))
            if min(times[index] - guess, guess - times[index - 1]) > self.tolerance:
                astray += 1
        return count, astray

    def realign(self, now, manual_offset=0.0):
        # Notes only show up on screen when they were not played in time, so a clock that runs ahead goes blind until it starts
        # missing. Each note seen could be any note of its lane nearby, but when the last few all sit the same distance from the
        # chart and the clock as it is cant explain them, the clock is what is off. Then it jumps there and stays in chart mode.
        recent = [(seen, lane) for seen, lane in self.recent if now - seen <= self.REALIGN_WINDOW]
        for count in range(self.REALIGN_SIGHTINGS, len(recent) + 1):
            voters = recent[-count:]
            positions = [(self.song_time(seen - manual_offset), self.lane_times[lane]) for seen, lane in voters]
            # every distance that would put one of them on a note of its lane, plus staying where it is
            shifts = [np.zeros(1)]
            for position, times in positions:
                shifts.append(position - times[(times > position - self.REALIGN_RANGE) & (times < position + self.REALIGN_RANGE)])
            candidates = np.unique(np.round(np.concatenate(shifts), 3))
            scores = np.zeros(candidates.size, dtype=np.int32)
            for position, times in positions:
                guess = position - candidates
                index = np.searchsorted(times, guess)
                scores += np.minimum(times[index] - guess, guess - times[index - 1]) <= self.REALIGN_TOLERANCE
            best = int(scores.max())
            if best < max(self.REALIGN_SIGHTINGS, math.ceil(0.8 * count)):
                continue
            top = candidates[scores == best]
            shift = float(np.median(top[top - top[0] <= 0.06]))
            if abs(shift) <= self.tolerance:
                continue # close enough, the normal fine tune handles that
            if best - int(scores[np.searchsorted(candidates, 0.0)]) < 3:
                continue # the clock as it is explains them nearly as well
            if np.any((scores >= best - 1) & (np.abs(candidates - shift) > 0.1)):
                continue # two places fit, wait for more notes
            # A clock that is this far off misses nearly every note, and every missed note shows up on screen. When most
            # notes of the last seconds were played fine and only a few sit one note over (a hit effect read as a note,
            # a note the chart does not have), the clock is not what is wrong
            here = self.song_time(now - manual_offset) - shift
            passed = sum(int(np.count_nonzero((times > here - self.REALIGN_RECENT) & (times <= here + 0.05))) for times in self.lane_times)
            seen_lately = sum(1 for seen, lane in self.recent if now - seen <= self.REALIGN_RECENT)
            if passed >= 6 and seen_lately < self.REALIGN_SEEN_SHARE * passed:
                return False

            offset, drift, reference = self.model
            previous = self.before_realign
            self.before_realign = (now, shift, drift, self.aligned)
            self.model = (offset + manual_offset + shift * (1 + drift), drift, reference)
            self.manual = False
            position = self.song_time(now)
            if previous is not None and now - previous[0] <= self.REALIGN_UNDO and abs(shift + previous[1]) <= 0.03:
                # straight back to where it came from: the jump before was wrong, and so is the speed it taught
                drift = previous[2]
                self.model = (self.wall_time(position) - position, drift, position)
                self.aligned = previous[3] if previous[3] is not None else position
                self.before_realign = None
            else:
                # the clock was right the last time it was lined up with the screen, so what built up since then is speed
                if self.aligned is not None and position - self.aligned >= 5:
                    drift = float(np.clip(drift + shift / (position - self.aligned), -self.MAX_DRIFT, self.MAX_DRIFT))
                    self.model = (self.wall_time(position) - position, drift, position)
                self.aligned = position
            # the fine tune starts over from the notes that voted
            self.matches.clear()
            self.last_matched = [None] * 5
            for seen, lane in voters:
                times = self.lane_times[lane]
                guess = self.song_time(seen)
                index = int(np.searchsorted(times, guess))
                nearest = times[index] if times[index] - guess < guess - times[index - 1] else times[index - 1]
                if abs(guess - nearest) <= self.REALIGN_TOLERANCE and self.last_matched[lane] != nearest:
                    self.last_matched[lane] = nearest
                    self.matches.append((float(nearest), seen - float(nearest)))
            self.fit()
            self.realigns += 1
            return True
        return False

    def fit(self):
        if not self.matches:
            return
        times = np.array([match[0] for match in self.matches])
        offsets = np.array([match[1] for match in self.matches])
        drift = self.model[1] # the last known speed stays until there are enough notes to measure it again
        if len(times) >= 10 and times[-1] - times[0] >= 4:
            first, second = np.triu_indices(len(times), 1)
            spacing = times[second] - times[first]
            usable = spacing > 1.0
            if usable.any():
                drift = float(np.clip(np.median((offsets[second] - offsets[first])[usable] / spacing[usable]), -self.MAX_DRIFT, self.MAX_DRIFT))
        reference = float(times[-1])
        self.model = (float(np.median(offsets - drift * (times - reference))), drift, reference)

    def try_lock(self, now):
        with self.mutex:
            if self.locked:
                return False
            sightings = [sighting for sighting in self.sightings if now - sighting[0] < 8]
            fewest = self.START_SIGHTINGS if self.hinted_position(now) is not None or any(closest is None for low, high, closest in self.expect) else 6
            if len(sightings) < fewest or len(sightings) == self.tried:
                return False
            self.tried = len(sightings)

            # every way the first few notes seen could line up with the chart
            candidates = np.unique(np.round(np.concatenate([seen - self.lane_times[lane][1:-1] for seen, lane in sightings[:self.LOCK_FROM]]), 3))
            if not candidates.size:
                return False
            scores = np.zeros(candidates.size, dtype=np.int32)
            for seen, lane in sightings:
                times = self.lane_times[lane]
                guess = seen - candidates
                index = np.searchsorted(times, guess)
                distance = np.minimum(times[index] - guess, guess - times[index - 1])
                scores += distance <= self.LOCK_TOLERANCE

            threshold = max(6, self.LOCK_SHARE * len(sightings))
            # first real note seen, a sighting with two more right after it so a stray false hit doesnt count
            first = next((self.history[index] for index in range(len(self.history) - 2) if self.history[index + 2] - self.history[index] <= 1.5), None)
            choices = []
            by = None
            best = None
            timed = self.hinted_position(now)
            if timed is not None:
                # the game's timer says where the song is to within a second, so only spots that agree with it are looked
                # at, and a few notes that fit there are enough
                near = np.abs((now - candidates) - timed) <= self.position_hint[2]
                top = int(scores[near].max()) if near.any() else 0
                if top >= max(self.START_SIGHTINGS, self.LOCK_SHARE * len(sightings)):
                    fits = near & (scores >= top - 1)
                    quiet = min(first - self.active_since, 1.5) if first is not None else 0.0
                    if quiet >= 0.3:
                        # the highway was being watched before the first note came, so the right spot has no note of the
                        # chart just before it. That tells one chord played again and again apart from its own repeats
                        before = first - candidates[fits]
                        empty = np.ones(before.size, dtype=bool)
                        for times in self.lane_times:
                            index = np.searchsorted(times, before - 0.06)
                            empty &= times[index - 1] < before - quiet + 0.05
                        if empty.any():
                            fits[np.flatnonzero(fits)[~empty]] = False
                            top = int(scores[fits].max())
                    tops = np.sort(candidates[fits & (scores == top)])
                    # with only a few notes a spot that fits one note less is still a rival, from six notes on it is not
                    rivals = candidates[fits & (scores >= (top if len(sightings) >= 6 else top - 1))]
                    # one spot only: the same notes one note over, or the next repeat of a short riff, would be a guess
                    if top >= max(self.START_SIGHTINGS, self.LOCK_SHARE * len(sightings)) and tops[-1] - tops[0] <= 0.09 and not np.any(np.abs(rivals - np.median(tops)) > 0.15):
                        best = float(np.median(tops))
                        by = "timer"
                if best is None and self.seen_since_hint < self.HINT_PATIENCE:
                    return False # keep collecting notes, the timer is right far more often than a lucky fit somewhere else
                # still nothing where the timer points after this many notes: the song length on file may be off for
                # this song, so the notes get to decide the way they did before there was a timer
            if best is None and first is not None:
                first_seen = first - candidates
                for low, high, closest in self.expect:
                    # only trust the song start hint if autoplay was on for a bit before the first note, otherwise it was turned on mid song
                    if closest is None and first - self.active_since < 1.5:
                        continue
                    near = (first_seen >= low) & (first_seen <= high) & (scores >= threshold)
                    if closest is None:
                        # the first notes of a song have nothing before them to be mixed up with, so a few that fit are enough.
                        # the chart takes over within a beat or two of the first note and the song starts without a key press
                        near |= (first_seen >= low) & (first_seen <= self.note_times[0] + self.START_SPAN) & (scores >= max(self.START_SIGHTINGS, self.LOCK_SHARE * len(sightings)))
                    if not near.any():
                        continue
                    near &= scores >= scores[near].max() - 1
                    if closest is None:
                        near &= scores == scores[near].max()
                        index = np.flatnonzero(near)[np.argmax(candidates[near])] # earliest spot
                    else:
                        # repeats close to where it stopped could fit too, wait for a few more notes before guessing the closest one
                        index = np.flatnonzero(near)[np.argmin(np.abs(first_seen[near] - closest))]
                        if np.any(near & (np.abs(candidates - candidates[index]) > 0.15)) and len(sightings) < 20:
                            return False
                    choices.append((int(scores[index]), float(candidates[index]), closest is None))
            # first hint wins a tie
            if best is None and choices:
                score, best, from_start = max(choices, key=lambda choice: choice[0])
                by = "start" if from_start else "notes"
            if best is None:
                best_score = int(scores.max())
                if best_score < max(threshold, self.LOCK_SIGHTINGS_BLIND):
                    return False
                # no idea where we are, so only lock when one spot clearly fits better than the rest
                best = float(candidates[scores == best_score].max())
                if np.any((scores >= best_score - 1) & (np.abs(candidates - best) > 0.15)):
                    return False
                by = "notes"
            if timed is not None and by != "timer":
                # the notes found a spot the timer did not agree with: the song length on file is off for this song.
                # remember by how much, so the timer still helps for the rest of it
                self.hint_bias += (now - best) - timed

            self.locked = True
            self.locked_by = by
            self.locked_at = now
            self.model = (best, 0.0, 0.0)
            for seen, lane in sightings:
                times = self.lane_times[lane]
                guess = seen - best
                index = int(np.searchsorted(times, guess))
                nearest = times[index] if times[index] - guess < guess - times[index - 1] else times[index - 1]
                if abs(guess - nearest) <= self.tolerance and self.last_matched[lane] != nearest:
                    self.last_matched[lane] = nearest
                    self.matches.append((float(nearest), seen - float(nearest)))
            self.fit()
            self.aligned = self.song_time(now)
            self.sightings.clear()
            self.version += 1
            return True

    def check(self, now, active):
        with self.mutex:
            if not self.locked:
                return None
            if self.song_time(now) > self.end + 3:
                self.reset()
                return "Song finished"
            if self.lost:
                # nothing seen lines up any more (paused, restarted, or too far off to pull back): play from the screen and look
                # for the song again around where the oldest note still remembered would be
                if self.locked_at is not None and now - self.locked_at < 20:
                    if self.locked_by == "timer":
                        self.timer_misses += 1 # the spot the timer pointed at did not hold
                    else:
                        self.hint_bias = 0.0 # the spot the notes picked against the timer did not hold either
                seen = self.sightings[max(0, len(self.sightings) - 12)][0] if self.sightings else now
                around = self.song_time(seen)
                self.unlock(keep_sightings=True, expect=[(around - 15, around + 5, around)])
                return "Lost sync with the highway"
            return None

    def check_summary(self, since):
        # median of how far the notes that fit were from the chart clock since then, in ms
        with self.mutex:
            errors = [error for when, error in self.checks if when >= since]
        return (float(np.median(errors)) * 1000, len(errors)) if errors else (None, 0)

    def drift_ms(self):
        return self.model[1] * 1000
