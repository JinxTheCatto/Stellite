# NOTE TO ANYBODY TRYING TO SELL THIS CODE (for some reason, its so bad vro)
# The source is under a AGPL-3.0 License, although I suspect you know that.
# If you try to sell this code, release it as closed source, or don't give credit to me and Stellite, as I already have been doing, I will take it down.

import time
import keyboard
import cv2
import numpy as np
import bettercam
import ctypes
from colorama import Fore, Back, Style, just_fix_windows_console
import os
import re
import sys
import json
import queue
import bisect
import threading
import win32api
import win32gui
import win32con
import charts
from overlay import Overlay

# Run from the stellite folder so the config and assets are always found
os.chdir(os.path.dirname(os.path.abspath(__file__)))
just_fix_windows_console()

# Get the real resolution, not the one windows display scaling makes up
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

# 1ms sleeps so chart presses land on time, and let threads swap more often than the default 5ms
ctypes.windll.winmm.timeBeginPeriod(1)
sys.setswitchinterval(0.001)

# Set console title
os.system("title Stellite Autoplayer Console")

# Clear the console
def cls():
    os.system('cls' if os.name == 'nt' else 'clear')
cls()

# Defaults for anything missing from config.json, so old configs keep working
default_config = {
    "min_confidence": 0.62,
    "min_tile_pixels_top_offset_scaled": 125,
    "tile_filename_suffix": "",
    "exit_key": "p",
    "keypress_holdtime": 0.05,
    "max_lane_cooldown": 0.02,
    "debug_positions": "false",
    "use_white_tile": "true",
    "white_tile_min_confidence": 0.62,
    "use_battlestage_tile": "false",
    "battlestage_tile_min_confidence": 0.62,
    "use_diamond_tile": "false",
    "diamond_tile_min_confidence": 0.95,
    "console_window_ontop": "true",
    "capture_fps": 200,
    "always_single_lanemode": "true",
    "single_lanemode_lanes": 5,
    "key_1": "d",
    "key_2": "f",
    "key_3": "j",
    "key_4": "k",
    "key_5": "l",
    "use_song_charts": "true",
    "instrument": "drums",
    "chart_timing_offset_ms": 0,
    "chart_nudge_step_ms": 5,
    "chart_sync_tolerance_ms": 50,
    "use_overdrive": "true",
    "overdrive_key": "space",
    "overdrive_timing_offset_ms": 0,
    "show_overlay": "true",
    "song_select_key": "[",
    "sync_key": "]",
    "nudge_earlier_key": "-",
    "nudge_later_key": "=",
}

# Load configuration
try:
    with open("config.json", "r") as file:
        config = {**default_config, **json.load(file)}
except Exception as e:
    print(Back.RED + Fore.WHITE + f"ERROR: Failed to load configuration file. {str(e)}" + Back.RESET + Fore.RESET)
    sys.exit()

def enabled(name):
    # config switches can be "true"/"false" or real true/false
    value = config[name]
    return value.strip().lower() == "true" if isinstance(value, str) else bool(value)

monitor_width = ctypes.windll.user32.GetSystemMetrics(0)
monitor_height = ctypes.windll.user32.GetSystemMetrics(1)

hwnd = None
if enabled("console_window_ontop"):
    hwnd_list = []
    def findit(hwnd, ctx):
        if win32gui.GetWindowText(hwnd).find("Stellite Autoplayer Console") != -1:
            hwnd_list.append(hwnd)
    win32gui.EnumWindows(findit, None)
    # prefer the real console window, windows terminal only shows up by its title
    console_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if console_hwnd in hwnd_list:
        hwnd = console_hwnd
    elif hwnd_list:
        hwnd = hwnd_list[0]
    if hwnd:
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        except Exception as e:
            print(Back.RED + Fore.WHITE + f"ERROR: {str(e)} while setting window position." + Back.RESET + Fore.RESET)
            hwnd = None
    else:
        print(Back.RED + Fore.WHITE + "ERROR: Console window handle not found." + Back.RESET + Fore.RESET)

# START
print(f'''
{Fore.RED}      :::::::: {Fore.YELLOW}::::::::::: {Fore.YELLOW}:::::::::: {Fore.GREEN}:::        {Fore.CYAN}:::        {Fore.BLUE}::::::::::: {Fore.MAGENTA}::::::::::: {Fore.MAGENTA}::::::::::
{Fore.RED}    :+:    :+:    {Fore.YELLOW}:+:     {Fore.YELLOW}:+:        {Fore.GREEN}:+:        {Fore.CYAN}:+:            {Fore.BLUE}:+:         {Fore.MAGENTA}:+:     {Fore.MAGENTA}:+:
{Fore.RED}   +:+           {Fore.YELLOW}+:+     {Fore.YELLOW}+:+        {Fore.GREEN}+:+        {Fore.CYAN}+:+            {Fore.BLUE}+:+         {Fore.MAGENTA}+:+     {Fore.MAGENTA}+:+
{Fore.RED}  +#++:++#++    {Fore.YELLOW}+#+     {Fore.YELLOW}+#++:++#   {Fore.GREEN}+#+        {Fore.CYAN}+#+            {Fore.BLUE}+#+         {Fore.MAGENTA}+#+     {Fore.MAGENTA}+#++:++#
{Fore.RED}        +#+    {Fore.YELLOW}+#+     {Fore.YELLOW}+#+        {Fore.GREEN}+#+        {Fore.CYAN}+#+            {Fore.BLUE}+#+         {Fore.MAGENTA}+#+     {Fore.MAGENTA}+#+
{Fore.RED}#+#    #+#    {Fore.YELLOW}#+#     {Fore.YELLOW}#+#        {Fore.GREEN}#+#        {Fore.CYAN}#+#            {Fore.BLUE}#+#         {Fore.MAGENTA}#+#     {Fore.MAGENTA}#+#
{Fore.RED}########     {Fore.YELLOW}###     {Fore.YELLOW}########## {Fore.GREEN}########## {Fore.CYAN}########## {Fore.BLUE}###########     {Fore.MAGENTA}###     {Fore.MAGENTA}##########
''')

print(Style.RESET_ALL + Fore.RED + "The first and best Fortnite Festival autoplayer")
print("Project by jinxthecat_")
print("Version 2")
print("Join our discord at https://discord.gg/PcW8tSN3r4")
print("THIS PROJECT IS UNDER THE AGPL-3 LICENSE!")
print("Song charts from fnfpaths, chart reading based on Festival OD Coach by Aknownthreat" + Fore.RESET)

if not enabled("always_single_lanemode"):
    number_of_lanes = None
    while number_of_lanes not in (4, 5):
        try:
            number_of_lanes = int(input("Number of lanes (4 = easy-hard, 5 = expert): "))
        except ValueError:
            number_of_lanes = None
        if number_of_lanes not in (4, 5):
            print(Back.RED + Fore.WHITE + "Number of lanes must be 4 or 5" + Back.RESET + Fore.RESET)
else:
    number_of_lanes = int(config["single_lanemode_lanes"])
    if number_of_lanes not in (4, 5):
        print(Back.RED + Fore.WHITE + "single_lanemode_lanes must be 4 or 5" + Back.RESET + Fore.RESET)
        sys.exit()

lane_keys = [str(config[f"key_{lane + 1}"]) for lane in range(number_of_lanes)]
overdrive_key = str(config["overdrive_key"])

# Logging from the hot paths goes through a queue so printing never slows down a press
log_queue = queue.Queue()
def log(message):
    log_queue.put(message)
def log_printer():
    while True:
        print(log_queue.get())
threading.Thread(target=log_printer, daemon=True).start()

def caps_lock():
    # low bit is the toggle, high bit is just the key being held
    return bool(win32api.GetKeyState(0x14) & 1)

# Song charts
# the chart does the playing once it is synced, the screen reader keeps it synced and takes over when it isnt
use_charts = enabled("use_song_charts")
if use_charts and number_of_lanes != 5:
    print(Fore.YELLOW + "Song charts are expert only (5 lanes), using screen reading only" + Fore.RESET)
    use_charts = False
songs = charts.load_songs() if use_charts else []
song_lengths = charts.load_song_lengths() if use_charts else {}
if use_charts and not songs:
    print(Fore.YELLOW + "No song list, using screen reading only" + Fore.RESET)
    use_charts = False

current = (None, None, [], []) # chart, sync, actions, action times. swapped all at once so threads never see half of a song
queued_charts = []
last_instrument = str(config["instrument"])
chart_offset = config["chart_timing_offset_ms"] / 1000 # minus is earlier, plus is later
overdrive_offset = config["overdrive_timing_offset_ms"] / 1000 # extra on top of chart_offset, only for overdrive

def describe_offset(seconds):
    # offsets in words, "-15" alone doesnt say which way it goes
    milliseconds = round(seconds * 1000, 1)
    if milliseconds == 0:
        return "on time (0 ms)"
    return f"{abs(milliseconds):g} ms {'earlier' if milliseconds < 0 else 'later'}"
picking = False

def build_actions(chart):
    actions = []
    hold = config["keypress_holdtime"]
    for lane in range(5):
        lane_notes = [note for note in chart["notes"] if note[1] == lane]
        for index, (start, note_lane, length) in enumerate(lane_notes):
            release = start + max(hold, length)
            if index + 1 < len(lane_notes):
                # let go a bit before the next note in this lane so it counts as a new press
                release = min(release, lane_notes[index + 1][0] - 0.01)
            actions.append((start, 1, "press", lane))
            actions.append((max(release, start + 0.005), 0, "release", lane))
    if enabled("use_overdrive"):
        for press_time, window_start, window_end in chart["overdrive"]:
            actions.append((press_time, 1, "overdrive", None))
            actions.append((press_time + hold, 0, "overdrive_release", None))
    # releases go before presses at the same time
    actions.sort(key=lambda action: (action[0], action[1]))
    return actions

def load_selected_chart():
    global last_instrument
    song = charts.prompt_song(songs)
    if song is None:
        return None
    instrument = charts.prompt_instrument(song, last_instrument)
    if instrument is None:
        return None
    last_instrument = instrument
    print(Fore.CYAN + "Reading the chart..." + Fore.RESET)
    try:
        chart = charts.load_chart(song, instrument, song_lengths)
    except Exception as e:
        print(Back.RED + Fore.WHITE + f"ERROR: Could not read the chart. {str(e)}" + Back.RESET + Fore.RESET)
        return None
    return chart

def activate_chart(chart, now=None):
    global current
    sync = charts.ChartSync(chart, config["chart_sync_tolerance_ms"] / 1000)
    sync.resume(time.perf_counter() if now is None else now)
    actions = build_actions(chart)
    current = (chart, sync, actions, [action[0] for action in actions])

    sustains = sum(1 for note in chart["notes"] if note[2] > 0)
    print(Fore.GREEN + Style.BRIGHT + f"{chart['name']} - {charts.INSTRUMENT_NAMES[instrument]} Expert" + Style.RESET_ALL)
    print(f"{len(chart['notes'])} notes, {sustains} sustains, {charts.clock(chart['length'] or chart['end'])} long")
    print(f"Overdrive path: {chart['path']} ({len(chart['overdrive'])} activations found)")
    # same as the in game timer, so its counting down when theres a song length
    for index, (press_time, window_start, window_end) in enumerate(chart["overdrive"]):
        at = chart["length"] - press_time if chart["length"] else press_time
        print(f"  {index + 1}. {charts.clock(at)}  on {chart['overdrive_labels'][index]}")
    if not enabled("use_overdrive"):
        print(Fore.YELLOW + "use_overdrive is off, overdrive wont be activated" + Fore.RESET)
    print(Fore.YELLOW + "Ready, go to Fortnite and turn caps lock on before the song starts" + Fore.RESET)

def pick_song():
    chart = load_selected_chart()
    if chart is None:
        if current[0] is not None:
            print(Fore.YELLOW + f"Keeping {current[0]['name']}" + Fore.RESET)
        else:
            print(Fore.YELLOW + "No song picked, using screen reading only. Press " + str.upper(config["song_select_key"]) + " to pick one later" + Fore.RESET)
        return
    activate_chart(chart)

def pick_initial_queue():
    pick_song()
    if current[0] is not None:
        add_queued_songs()

def add_queued_songs():
    while charts.prompt_queue_another():
        chart = load_selected_chart()
        if chart is None:
            break
        queued_charts.append(chart)
        print(Fore.GREEN + f"Added {chart['name']} - {charts.INSTRUMENT_NAMES[chart['instrument']]} to queue ({len(queued_charts)} queued)" + Fore.RESET)

def pick_after_queue_finished():
    global current, picking
    picking = True
    try:
        if not charts.prompt_queue_another("Queue finished. Pick another song? (Y/N)"):
            current = (None, None, [], [])
            print(Fore.YELLOW + f"Queue is empty. Press {config['song_select_key']} later to choose a song." + Fore.RESET)
            return
        chart = load_selected_chart()
        if chart is None:
            current = (None, None, [], [])
            print(Fore.YELLOW + f"No song selected. Press {config['song_select_key']} later to choose one." + Fore.RESET)
            return
        activate_chart(chart)
        add_queued_songs()
    finally:
        picking = False

def save_offset():
    # write the tuned timing into config.json without touching anything else in it
    value = f"{round(chart_offset * 1000, 1):g}"
    try:
        with open("config.json", "r", newline="") as file:
            text = file.read()
        text, found = re.subn(r'("chart_timing_offset_ms"\s*:\s*)-?[\d.]+', lambda match: match.group(1) + value, text)
        if not found:
            text = text.replace("{", '{\n    "chart_timing_offset_ms": ' + value + ",", 1)
        with open("config.json", "w", newline="") as file:
            file.write(text)
        return True
    except Exception as e:
        log(Back.RED + Fore.WHITE + f"ERROR: Could not save the timing to config.json. {str(e)}" + Back.RESET + Fore.RESET)
        return False

if use_charts:
    print(Fore.CYAN + Style.BRIGHT + "\nHow it plays" + Style.RESET_ALL)
    print("  1. Pick a song and instrument below; answer Y to queue more songs")
    print("  2. In Fortnite, turn caps lock on before the song starts")
    print("  3. Stellite plays from the screen for the first few notes, then syncs up and plays from the chart")
    print(Fore.CYAN + Style.BRIGHT + "Hotkeys (they work while Fortnite is open)" + Style.RESET_ALL)
    print(f"  {config['song_select_key']}   Pick a different song. Click this window afterwards to type the name")
    print(f"  {config['sync_key']}   Press right when GO shows at the start of a song. Only needed if the overlay keeps saying syncing")
    print(f"  {config['nudge_earlier_key']}   Play notes {config['chart_nudge_step_ms']} ms earlier. Press it while playing if you get Goods instead of Perfects")
    print(f"  {config['nudge_later_key']}   Play notes {config['chart_nudge_step_ms']} ms later, if you went too far")
    print(f"  {str.upper(config['exit_key'])}   Exit")
    print(f"Timing: notes play {describe_offset(chart_offset)}. Change it with {config['nudge_earlier_key']} and {config['nudge_later_key']} while playing, it saves by itself")
    if overdrive_offset:
        print(f"Overdrive plays another {describe_offset(overdrive_offset)} than the notes (overdrive_timing_offset_ms)")
    pick_initial_queue()

print(Fore.GREEN + f"WILL ONLY AUTOPLAY WHILE CAPS LOCK IS ON! CURRENT CAPSLOCK STATUS: " + ("On" if caps_lock() else "Off"))
print(Fore.YELLOW + f"Resolution: {monitor_width}x{monitor_height}" + Fore.RESET)
print(f"Program started, press {str.upper(config['exit_key'])} to exit")

# Match images, the closest resolution gets scaled if there are none for this one
asset_heights = sorted(
    (int(folder) for folder in os.listdir("assets") if folder.isdigit() and os.path.isdir(os.path.join("assets", folder))),
    key=lambda folder_height: (folder_height != monitor_height, abs(folder_height - monitor_height))
)

def load_template(name):
    suffix = config["tile_filename_suffix"]
    for folder_height in asset_heights:
        for filename in (f"{name}{suffix}.png", f"{name}.png"):
            path = os.path.join("assets", str(folder_height), filename)
            if not os.path.isfile(path):
                continue
            image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if image is None:
                continue
            if filename != f"{name}{suffix}.png":
                print(Fore.YELLOW + f"No {name}{suffix}.png, using {name}.png" + Fore.RESET)
            if folder_height != monitor_height:
                scale = monitor_height / folder_height
                image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
                print(Fore.YELLOW + f"No {monitor_height}p {name} image, scaling the {folder_height}p one. You might need to tune the confidence values" + Fore.RESET)
            return image.astype(np.uint8)
    return None

# 1080p values:
region_width = 555 if number_of_lanes == 4 else 696 # width of the capture region
region_height = 180 # height of the capture region
height_offset = 190 # higher number is looking higher :O
# scale values
scale_factor = 1080 / monitor_height
min_tile_pixels_top_offset = int(config["min_tile_pixels_top_offset_scaled"] // scale_factor)
if scale_factor != 1:
    region_width = int(region_width // scale_factor)
    region_height = int(region_height // scale_factor)
    height_offset = int(height_offset // scale_factor)

region_fromleft = int(((monitor_width - region_width) // 2) + (8 // scale_factor) if number_of_lanes == 5 else ((monitor_width - region_width) // 2) + 1) # higher offset is looking more right. idk why this is needed since it should be centered. fortnite festival is slightly to the right?
region_fromtop = (monitor_height - region_height) - height_offset
width = region_fromleft + region_width
height = region_fromtop + region_height
section_size = region_width // number_of_lanes

tile = load_template("tile")
if tile is None:
    print(Back.RED + Fore.WHITE + "No match images in the assets folder found! Please make sure you have an image made." + Back.RESET + Fore.RESET)
    sys.exit()
templates = [(tile, config["min_confidence"])]
for name, option, confidence in (
    ("white", "use_white_tile", "white_tile_min_confidence"),
    ("battlestage", "use_battlestage_tile", "battlestage_tile_min_confidence"),
    ("diamond", "use_diamond_tile", "diamond_tile_min_confidence"),
):
    if enabled(option):
        image = load_template(name)
        if image is None:
            print(Fore.YELLOW + f"No {name} match image found, turning {option} off" + Fore.RESET)
        else:
            templates.append((image, config[confidence]))

main_camera = bettercam.create(output_color = "GRAY", max_buffer_len=64)
main_camera.start(region = (region_fromleft, region_fromtop, width, height), target_fps=config["capture_fps"])

running = True
autoplaying = caps_lock()

lane_busy = [False] * number_of_lanes
lane_lock = threading.Lock()
lane_last_seen = [0.0] * 5
sighting_lock = threading.Lock()

def truncate(n, decimals = 0):
    multiplier = 10 ** decimals
    return int(n * multiplier) / multiplier

def press(lane):
    key = lane_keys[lane]
    log(Fore.GREEN + f"{time.time()}: Pressing {str.capitalize(key)}" + Fore.RESET)
    keyboard.press(key)
    time.sleep(config["keypress_holdtime"])
    keyboard.release(key)
    # lane cooldown
    time.sleep(config["max_lane_cooldown"])
    lane_busy[lane] = False

def press_tile(lane):
    # the lane is marked busy right away, otherwise every frame the tile is visible starts another press
    with lane_lock:
        if lane_busy[lane]:
            if enabled("debug_positions"):
                log(Fore.RED + f"Skipping lane {str.capitalize(lane_keys[lane])} due to cooldown" + Fore.RESET)
            return
        lane_busy[lane] = True
    threading.Thread(target=press, args=(lane,), daemon=True).start()

def tile_seen(lane, frame_time):
    with sighting_lock:
        last = lane_last_seen[lane]
        lane_last_seen[lane] = max(last, frame_time)
    sync = current[1]
    # only the first frame a tile shows up in counts, thats when it reached the press line
    if sync is not None and frame_time - last > 0.035:
        sync.add_sighting(frame_time, lane)

def press_tiles(rectangles, results, crop_top, frame_time):
    sync = current[1]
    from_chart = sync is not None and sync.locked
    for (x, y, w, h) in rectangles:
        tile_position = (x + (w // 2), y + (h // 2))
        #print(f"Found tile at {tile_position} confidence:
        lane = min(tile_position[0] // section_size, number_of_lanes - 1)
        if tile_position[1] >= min_tile_pixels_top_offset:
            tile_seen(lane, frame_time)
            # once the chart is synced it does the pressing, the screen just keeps it synced
            if not from_chart:
                press_tile(lane)

        if enabled("debug_positions"):
            log(f"Found tile in lane {str.capitalize(lane_keys[lane])} with confidence {truncate(results[min(y - crop_top, results.shape[0] - 1)][x], 2)}")

def tile_logic(screenshot_np, frame_time, template, min_confidence, crop_top):
    # only the bottom of the capture can get pressed, so only search that part. a lot faster
    results = cv2.matchTemplate(screenshot_np[crop_top:], template, cv2.TM_CCOEFF_NORMED)
    locations = np.where(results >= min_confidence)

    rectangles = []
    for positions in zip(*locations[::-1]):
        rectangle = (int(positions[0]), int(positions[1]) + crop_top, int(template.shape[1]), int(template.shape[0]))
        # groupRectangles throws out rectangles that are alone, so each one goes in twice
        rectangles.append(rectangle)
        rectangles.append(rectangle)
    rectangles, weights = cv2.groupRectangles(rectangles, 1, 0.2)

    press_tiles(rectangles, results, crop_top, frame_time)

# Capture and detection threads
# one worker per match image, each one always grabs the newest frame so nothing piles up
frame_condition = threading.Condition()
latest_frame = None
latest_frame_time = 0.0
frame_number = 0

def capture_loop():
    global latest_frame, latest_frame_time, frame_number
    while running:
        screenshot_np = main_camera.get_latest_frame()
        frame_time = time.perf_counter()
        if screenshot_np is None:
            continue
        with frame_condition:
            latest_frame = screenshot_np
            latest_frame_time = frame_time
            frame_number += 1
            frame_condition.notify_all()

def detection_worker(template, min_confidence):
    crop_top = max(0, min(min_tile_pixels_top_offset - template.shape[0] // 2 - 4, region_height - template.shape[0]))
    seen = 0
    while running:
        with frame_condition:
            if frame_number == seen:
                frame_condition.wait(0.1)
            if frame_number == seen:
                continue
            screenshot_np, frame_time, seen = latest_frame, latest_frame_time, frame_number
        if autoplaying and not picking:
            tile_logic(screenshot_np, frame_time, template, min_confidence, crop_top)

# Chart player
def chart_player():
    held = set()
    overdrive_held = False
    following = None
    index = 0
    while running:
        chart, sync, actions, action_times = current
        if sync is None or not sync.locked or not autoplaying or picking or following is None or following != (sync, sync.version):
            # let go of everything when the chart stops or jumps
            for lane in held:
                keyboard.release(lane_keys[lane])
            held.clear()
            if overdrive_held:
                keyboard.release(overdrive_key)
                overdrive_held = False
            if sync is None or not sync.locked or not autoplaying or picking:
                following = None
                time.sleep(0.005)
                continue
            following = (sync, sync.version)
            index = bisect.bisect_left(action_times, sync.song_time(time.perf_counter()) - chart_offset + 0.005)

        if index >= len(actions):
            time.sleep(0.01)
            continue
        action_time, order, kind, lane = actions[index]
        target = sync.wall_time(action_time) + chart_offset + (overdrive_offset if kind.startswith("overdrive") else 0)
        wait = target - time.perf_counter()
        if wait > 0.002:
            time.sleep(min(wait - 0.0015, 0.01))
            continue
        while time.perf_counter() < target:
            pass
        late = time.perf_counter() - target

        if kind == "press":
            # way too late is a miss anyway, dont press into the next note
            if late < 0.05:
                keyboard.press(lane_keys[lane])
                held.add(lane)
                log(Fore.GREEN + f"{time.time()}: Pressing {str.capitalize(lane_keys[lane])} (chart)" + Fore.RESET)
        elif kind == "release":
            if lane in held:
                keyboard.release(lane_keys[lane])
                held.discard(lane)
        elif kind == "overdrive":
            if late < 0.1:
                keyboard.press(overdrive_key)
                overdrive_held = True
                log(Fore.MAGENTA + Style.BRIGHT + f"{time.time()}: Activating overdrive" + Style.RESET_ALL)
        elif kind == "overdrive_release":
            if overdrive_held:
                keyboard.release(overdrive_key)
                overdrive_held = False
        index += 1

threading.Thread(target=capture_loop, daemon=True).start()
for template, min_confidence in templates:
    threading.Thread(target=detection_worker, args=(template, min_confidence), daemon=True).start()
if use_charts:
    threading.Thread(target=chart_player, daemon=True).start()

overlay = None
if use_charts and enabled("show_overlay"):
    try:
        overlay = Overlay()
        overlay.set_clickthrough(autoplaying)
    except Exception as e:
        print(Fore.YELLOW + f"Could not open the overlay: {str(e)}" + Fore.RESET)
        overlay = None

def overlay_text(now):
    chart, sync, actions, action_times = current
    if sync is None:
        return ("-:--", f"{config['song_select_key']} to pick a song" if autoplaying else "caps lock off", "dim", "dim")
    # festival style song timer, counts down from the song length like the one in game
    length = chart["length"]
    if not sync.locked:
        small = f"syncing, {config['sync_key']} on GO if stuck" if autoplaying else "caps lock off"
        return (charts.clock(length) if length else "-:--", small, "dim", "white" if length else "dim")
    song_time = sync.song_time(now)
    timer = charts.clock(length - song_time) if length else "-:--"
    if not autoplaying:
        return (timer, "caps lock off", "dim", "white")
    overdrive = list(enumerate(chart["overdrive"])) if enabled("use_overdrive") else []
    labels = chart["overdrive_labels"]
    shift = chart_offset + overdrive_offset
    for index, (press_time, window_start, window_end) in overdrive:
        if 0 <= song_time - press_time - shift < 0.85:
            return (timer, f"OD NOW  {labels[index]}", "now", "white")
    upcoming = [(index, press_time) for index, (press_time, window_start, window_end) in overdrive if press_time + shift > song_time]
    if upcoming:
        index, press_time = upcoming[0]
        # the overdrive line uses the same countdown, so it matches the timer
        at = length - press_time - shift if length else press_time + shift - song_time
        return (timer, f"OD {charts.clock(at)}  {labels[index]}", "accent", "white")
    return (timer, "path done" if overdrive else "synced", "good", "white")

overlay_note = ("", 0.0) # short message that covers the bottom line for a bit

hotkeys_down = {}
def hotkey(key):
    # true once per key press, not every loop while its held
    pressed = keyboard.is_pressed(key)
    was_pressed = hotkeys_down.get(key, False)
    hotkeys_down[key] = pressed
    return pressed and not was_pressed

last_overlay = 0.0
synced_before = False
try:
    while not keyboard.is_pressed(config['exit_key']):
        now = time.perf_counter()
        capslock_status = caps_lock()
        if capslock_status != autoplaying:
            autoplaying = capslock_status
            if current[1] is not None and autoplaying:
                current[1].resume(now)
            if overlay is not None:
                overlay.set_clickthrough(autoplaying)

        chart, sync, actions, action_times = current
        if sync is not None:
            if sync.try_lock(now):
                log(Fore.GREEN + Style.BRIGHT + f"Synced to {chart['name']} at {charts.clock(sync.song_time(now))}, playing from the chart" + Style.RESET_ALL)
                if not synced_before:
                    synced_before = True
                    log(Fore.CYAN + f"Getting Goods instead of Perfects? Press {config['nudge_earlier_key']} a few times while playing until they turn into Perfects" + Fore.RESET)
            message = sync.check(now, autoplaying)
            if message:
                log(Fore.YELLOW + f"{message}, reading the screen until it syncs again" + Fore.RESET)
                if message == "Song finished" and queued_charts:
                    next_chart = queued_charts.pop(0)
                    activate_chart(next_chart, now)
                    chart, sync, actions, action_times = current
                    log(Fore.CYAN + f"Starting next queued song: {chart['name']} ({len(queued_charts)} remaining)" + Fore.RESET)
                elif message == "Song finished":
                    pick_after_queue_finished()
                    chart, sync, actions, action_times = current

        if use_charts and hotkey(config["song_select_key"]):
            picking = True
            print(Fore.MAGENTA + Style.BRIGHT + "\nClick this window to type the song name (autoplay is paused until you pick)" + Style.RESET_ALL)
            pick_song()
            picking = False
            if current[1] is not None:
                current[1].resume(time.perf_counter())
        if sync is not None and hotkey(config["sync_key"]):
            # pressing it mid song by accident would throw off a good sync, so only use it when the screen hasnt synced
            if sync.locked and not sync.manual:
                log(Fore.YELLOW + f"Already synced from the screen, {config['sync_key']} isnt needed" + Fore.RESET)
                overlay_note = ("already synced", now + 1.5)
            else:
                sync.start_now(now)
                log(Fore.GREEN + "Synced on GO, the screen reader will fine tune it when it can" + Fore.RESET)
                overlay_note = ("synced on GO", now + 1.5)
        for key, step in ((config["nudge_earlier_key"], -1), (config["nudge_later_key"], 1)):
            if use_charts and hotkey(key):
                chart_offset += step * config["chart_nudge_step_ms"] / 1000
                saved = save_offset()
                timing = describe_offset(chart_offset)
                log(Fore.CYAN + f"Notes now play {timing}" + (f" (saved, chart_timing_offset_ms is {round(chart_offset * 1000, 1):g})" if saved else "") + Fore.RESET)
                overlay_note = (f"notes {timing}", now + 1.5)

        if overlay is not None and now - last_overlay > 0.05:
            last_overlay = now
            big, small, color, big_color = overlay_text(now)
            if now < overlay_note[1]:
                small, color = overlay_note[0], "good"
            overlay.show(big, small, color, big_color)
        time.sleep(0.005)
except KeyboardInterrupt:
    pass

# STOP
running = False
for key in lane_keys + [overdrive_key]:
    keyboard.release(key)
main_camera.stop()
if overlay is not None:
    overlay.close()
if hwnd:
    win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
ctypes.windll.winmm.timeEndPeriod(1)

print(Fore.WHITE + Back.RED + "Stop key pressed. Exiting Stellite..." + Fore.RESET + Back.RESET)
