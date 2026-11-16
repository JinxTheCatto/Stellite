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
import threading
import unicodedata
import urllib.parse
import urllib.request
from collections import deque
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
SONGS_MAX_AGE = 12 * 60 * 60 # redownload the song list twice a day

# fnfp.js field prefix -> instrument. the site names them weird, m is normal bass and b is pro bass
INSTRUMENTS = {"d": "drums", "l": "lead", "m": "bass", "v": "vocals", "g": "pro_lead", "b": "pro_bass"}
INSTRUMENT_NAMES = {"drums": "Drums", "lead": "Lead", "bass": "Bass", "vocals": "Vocals", "pro_lead": "Pro Lead", "pro_bass": "Pro Bass"}

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

def http_get(url, timeout = 60):
    request = urllib.request.Request(url, headers={"User-Agent": "Stellite"})
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
            stars = cv2.matchTemplate(band[1:13], STAR, cv2.TM_CCORR)[0] / STAR.sum()
            score = np.zeros(band.shape[1], dtype=np.float32)
            score[5 : 5 + circles.size] = circles
            score[5 : 5 + stars.size] = np.maximum(score[5 : 5 + stars.size], stars)
            last_x = -100
            for x in np.flatnonzero(score >= 0.85):
                if score[x] < score[max(0, x - 3) : x + 4].max() or x - last_x < 4:
                    continue
                last_x = x
                x = int(x) + LEFT_MARGIN - 7
                notes.append((snap_beat(start, x), lane, row_index, x))
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

    notes = []
    note_beats = set()
    for beat, lane, row_index, x in find_notes(image, rows):
        end = sustain_end(image, rows, row_index, x, lane)
        start_time = float(to_seconds(beat))
        length = float(to_seconds(end)) - start_time if end is not None else 0.0
        notes.append((start_time, lane, max(0.0, length)))
        note_beats.add(beat)
    if not notes:
        raise ValueError("No notes found in the path image")
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
        "overdrive": overdrive,
        "end": max(time + length for time, lane, length in notes),
        "tempos": tempos,
    }

def load_chart(song, instrument, lengths = None):
    image_name = song["paths"][instrument]["image"]
    if not IMAGE_NAME_RE.match(image_name):
        raise ValueError(f"Bad path image name {image_name}")
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
    print("Instrument: " + "  ".join(
        (Fore.GREEN + Style.BRIGHT if instrument == default else "") + f"[{index + 1}] {INSTRUMENT_NAMES[instrument]}" + Style.RESET_ALL
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
# Once it is locked the chart does the playing and every note seen on screen just keeps the clock lined up

class ChartSync:
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
        self.reset()

    def reset(self, expect = "start"):
        with self.mutex:
            self.sightings = deque(maxlen=40)
            self.matches = deque(maxlen=32)
            self.recent = deque(maxlen=10)
            self.last_matched = [None] * 5
            self.last_sighting = 0.0
            self.history = [] # first few sightings since the last reset
            self.tried = 0
            self.locked = False
            self.manual = False
            self.model = (0.0, 0.0, 0.0) # offset, drift, reference
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

    def start_now(self, now):
        # manual sync, press on GO. song time 0 is now
        with self.mutex:
            self.reset()
            self.model = (now, 0.0, 0.0)
            self.locked = True
            self.manual = True
            self.active_since = now

    def resume(self, now):
        self.active_since = now

    def add_sighting(self, now, lane):
        with self.mutex:
            self.last_sighting = now
            self.sightings.append((now, lane))
            if not self.locked:
                if len(self.history) < 12:
                    self.history.append(now)
                return
            times = self.lane_times[lane]
            guess = self.song_time(now)
            index = int(np.searchsorted(times, guess))
            nearest = times[index] if times[index] - guess < guess - times[index - 1] else times[index - 1]
            if abs(now - self.wall_time(nearest)) > self.tolerance:
                self.recent.append(False)
                return
            self.recent.append(True)
            if self.last_matched[lane] == nearest:
                return
            self.last_matched[lane] = nearest
            self.matches.append((float(nearest), now - float(nearest)))
            self.manual = False
            self.fit()

    def fit(self):
        times = np.array([match[0] for match in self.matches])
        offsets = np.array([match[1] for match in self.matches])
        drift = 0.0
        if len(times) >= 10 and times[-1] - times[0] >= 3:
            first, second = np.triu_indices(len(times), 1)
            spacing = times[second] - times[first]
            usable = spacing > 0.5
            if usable.any():
                drift = float(np.clip(np.median((offsets[second] - offsets[first])[usable] / spacing[usable]), -0.01, 0.01))
        reference = float(times[-1])
        self.model = (float(np.median(offsets - drift * (times - reference))), drift, reference)

    def try_lock(self, now):
        with self.mutex:
            if self.locked:
                return False
            sightings = [sighting for sighting in self.sightings if now - sighting[0] < 8]
            if len(sightings) < 6 or len(sightings) == self.tried:
                return False
            self.tried = len(sightings)

            # every way the first few notes seen could line up with the chart
            candidates = np.unique(np.round(np.concatenate([seen - self.lane_times[lane][1:-1] for seen, lane in sightings[:4]]), 3))
            if not candidates.size:
                return False
            scores = np.zeros(candidates.size, dtype=np.int32)
            for seen, lane in sightings:
                times = self.lane_times[lane]
                guess = seen - candidates
                index = np.searchsorted(times, guess)
                distance = np.minimum(times[index] - guess, guess - times[index - 1])
                scores += distance <= self.tolerance

            threshold = max(6, 0.6 * len(sightings))
            # first real note seen, a sighting with two more right after it so a stray false hit doesnt count
            first = next((self.history[index] for index in range(len(self.history) - 2) if self.history[index + 2] - self.history[index] <= 1.5), None)
            choices = []
            if first is not None:
                first_seen = first - candidates
                for low, high, closest in self.expect:
                    # only trust the song start hint if autoplay was on for a bit before the first note, otherwise it was turned on mid song
                    if closest is None and first - self.active_since < 1.5:
                        continue
                    near = (first_seen >= low) & (first_seen <= high) & (scores >= threshold)
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
                    choices.append((int(scores[index]), float(candidates[index])))
            # first hint wins a tie
            best = max(choices, key=lambda choice: choice[0])[1] if choices else None
            if best is None:
                best_score = int(scores.max())
                if best_score < threshold:
                    return False
                # no idea where we are, so only lock when one spot clearly fits better than the rest
                best = float(candidates[scores == best_score].max())
                if np.any((scores >= best_score - 1) & (np.abs(candidates - best) > 0.15)):
                    return False

            self.locked = True
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
            if len(self.recent) >= 10 and sum(self.recent) < 0.5 * len(self.recent):
                self.unlock(keep_sightings=True)
                return "Lost sync with the highway"
            quiet_since = max(self.last_sighting, self.active_since)
            if active and not self.manual and now - quiet_since > 1.5:
                # notes should have come by but nothing was seen, paused or restarted
                start = self.song_time(quiet_since) + 0.2
                expected = np.count_nonzero((self.note_times > start) & (self.note_times < self.song_time(now)))
                if expected >= 6:
                    # most likely paused, so look for it again around where it stopped
                    stopped = self.song_time(quiet_since)
                    self.unlock(expect=[(stopped - 15, stopped + 5, stopped), self.song_start()])
                    return "No notes seen on the highway"
            return None

    def drift_ms(self):
        return self.model[1] * 1000
