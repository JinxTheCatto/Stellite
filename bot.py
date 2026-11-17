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
import glob
import sys
import json
import queue
import bisect
import shutil
import threading
import win32api
import win32gui
import win32con
import charts
from emote_prompt import EmotePromptReader
from screen_recording import ScreenRecorder
from screen_learning import ScreenChartLearner
from overlay import Overlay
from difflib import SequenceMatcher
from song_detect import ReadyScreenReader, to_1080, fold
from run_logging import ManualKeyLogger, SessionLog, clear_old_runs, format_skipped_key
from timing_tuner import TimingTuner, VisualGradeReader

# Run from the stellite folder so the config and assets are always found
os.chdir(os.path.dirname(os.path.abspath(__file__)))
just_fix_windows_console()

# every start clears the logs and recordings of earlier runs, the last run that played is kept in data/last_run
old_runs_removed, old_runs_kept = clear_old_runs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
# every note the screen reader sees, so a run can be replayed through the chart sync afterwards
sightings_file = None
sightings_lock = threading.Lock()

def record_sighting(frame_time, lane, sync):
    global sightings_file
    with sightings_lock:
        if sightings_file is None:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "logs", time.strftime("sightings-%Y%m%d-%H%M%S.csv"))
            sightings_file = open(path, "w", encoding="utf-8", buffering=1) # written line by line so it is there if the bot gets killed
            sightings_file.write("wall_time,lane,locked,song_time" + chr(10))
        song_time = f"{sync.song_time(frame_time):.4f}" if sync.locked else ""
        sightings_file.write(f"{frame_time:.4f},{lane},{int(sync.locked)},{song_time}" + chr(10))

session_log = SessionLog(os.path.join(os.path.dirname(__file__), "data", "logs"))

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
    "min_confidence": 0.95,
    "screen_learning_confidence": 0.55,
    "min_tile_pixels_top_offset_scaled": 125,
    "tile_filename_suffix": "",
    "exit_key": "ctrl+q",
    "keypress_holdtime": 0.05,
    "max_lane_cooldown": 0.02,
    "debug_positions": "false",
    "use_white_tile": "true",
    "white_tile_min_confidence": 0.95,
    "use_battlestage_tile": "false",
    "battlestage_tile_min_confidence": 0.95,
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
    "auto_detect_song": "true",
    "screen_fine_tune": "true",
    "record_screen": "true",
    "song_select_key": "[",
    "sync_key": "]",
    "restart_key": "r",
    "read_screen_key": "\\",
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
        # happens in terminals without a real console window (like editor terminals), only the keep-on-top is lost
        print(Fore.YELLOW + "Could not find the console window, it will not be kept on top" + Fore.RESET)

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
lane_key_down = [False] * number_of_lanes
overdrive_key_down = False
lane_state_lock = threading.Lock()
console_output_lock = threading.RLock()
lane_status_changed = threading.Event()
lane_status_active = False

def lane_status_text():
    with lane_state_lock:
        tiles = [
            (f" {key.upper()} ", lane_key_down[lane])
            for lane, key in enumerate(lane_keys)
        ]
        tiles.append((f" {overdrive_key.upper()} ", overdrive_key_down))
    colored_tiles = [
        (Back.GREEN + Fore.BLACK + label + Back.RESET + Fore.RESET)
        if pressed else (Fore.WHITE + Back.BLACK + label + Back.RESET + Fore.RESET)
        for label, pressed in tiles
    ]
    text = "Lane keys: " + " ".join(colored_tiles)
    visible_width = len("Lane keys: ") + sum(len(label) for label, _ in tiles) + len(tiles) - 1
    padding = max(0, (shutil.get_terminal_size(fallback=(80, 24)).columns - visible_width) // 2)
    return " " * padding + text

def render_lane_status():
    with console_output_lock:
        if not lane_status_active:
            return
        sys.stdout.write("\r\033[2K" + lane_status_text())
        sys.stdout.flush()

def lane_status_worker():
    while running:
        if lane_status_changed.wait(0.5):
            lane_status_changed.clear()
            render_lane_status()

def start_lane_status():
    global lane_status_active
    with console_output_lock:
        lane_status_active = True
        sys.stdout.write(lane_status_text())
        sys.stdout.flush()

def stop_lane_status():
    global lane_status_active
    with console_output_lock:
        if lane_status_active:
            sys.stdout.write("\r\033[2K\n")
            sys.stdout.flush()
            lane_status_active = False

def console_print(message):
    with console_output_lock:
        session_log.write(message)
        if lane_status_active:
            sys.stdout.write("\r\033[2K" + str(message) + "\n")
            sys.stdout.write(lane_status_text())
            sys.stdout.flush()
        else:
            print(message)

def log(message):
    log_queue.put(message)
def log_printer():
    while True:
        message = log_queue.get()
        try:
            console_print(message)
        finally:
            log_queue.task_done()
threading.Thread(target=log_printer, daemon=True).start()
console_print(Fore.CYAN + f"Session log: {session_log.path}" + Fore.RESET)
if old_runs_kept:
    console_print(Fore.CYAN + f"Kept the last run's log and newest recordings in data/last_run ({old_runs_kept} files), older ones are deleted" + Fore.RESET)
elif old_runs_removed:
    console_print(Fore.CYAN + f"Deleted {old_runs_removed} old log and recording files" + Fore.RESET)

screen_recorder = ScreenRecorder(os.path.join(os.path.dirname(__file__), "data", "recordings"))

def start_screen_recording(chart):
    if not enabled("record_screen"):
        return
    try:
        output_path = screen_recorder.start(chart.get("shortname") or chart["name"])
    except (OSError, RuntimeError) as e:
        log(Fore.RED + f"ERROR: Could not start FFmpeg screen recording: {e}" + Fore.RESET)
        return
    if output_path is not None:
        log(Fore.CYAN + f"Started full-screen recording: {output_path}" + Fore.RESET)

def stop_screen_recording():
    try:
        output_path = screen_recorder.stop()
    except (OSError, RuntimeError) as e:
        log(Fore.RED + f"ERROR: Could not finish FFmpeg screen recording: {e}" + Fore.RESET)
        return
    if output_path is not None:
        log(Fore.GREEN + f"Saved screen recording: {output_path}" + Fore.RESET)

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
screen_learner = None
screen_learning_lock = threading.Lock()
last_instrument = str(config["instrument"])
chart_offset = config["chart_timing_offset_ms"] / 1000 # minus is earlier, plus is later
overdrive_offset = config["overdrive_timing_offset_ms"] / 1000 # extra on top of chart_offset, only for overdrive
timing_tuner = None
timing_tuner_lock = threading.RLock()

def describe_offset(seconds):
    # offsets in words, "-15" alone doesnt say which way it goes
    milliseconds = round(seconds * 1000, 1)
    if milliseconds == 0:
        return "on time (0 ms)"
    return f"{abs(milliseconds):g} ms {'earlier' if milliseconds < 0 else 'later'}"
picking = False

def build_actions(chart):
    hold = config["keypress_holdtime"]
    # presses, holds and releases for the notes, including the ones that are hit by letting go (lift notes)
    actions = charts.note_actions(chart, hold)

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
    return load_song_chart(song, instrument)

def load_song_chart(song, instrument, say=print):
    learned_chart = charts.load_learned_chart(song, instrument)
    try:
        chart = charts.load_chart(song, instrument, song_lengths)
    except Exception as e:
        say(Back.RED + Fore.WHITE + f"ERROR: Could not read the chart for {song['name']}. {str(e)}" + Back.RESET + Fore.RESET)
        return None
    chart["shortname"] = song.get("shortname")
    chart["learned"] = False
    if learned_chart is not None:
        issue = charts.learned_chart_quality(learned_chart, chart)
        if issue is None:
            say(Fore.CYAN + f"Using the saved screen-learned chart for {song['name']}" + Fore.RESET)
            learned_chart["lift_notes"] = chart.get("lift_notes", []) # which notes are hit by letting go only shows in the source chart
            return learned_chart
        say(Fore.YELLOW + f"Saved screen chart is inconsistent ({issue}); using the source chart instead" + Fore.RESET)
    return chart

# Ready screen
# Before each set the game shows the setlist and your part, read it so nobody has to type the song in
ready_screen_setlists = queue.Queue()

LAST_PART_FILE = os.path.join("data", "last_part.txt")

def remember_part(instrument):
    try:
        with open(LAST_PART_FILE, "w") as file:
            file.write(instrument)
    except OSError:
        pass

def remembered_part():
    # the part that was last read off the ready screen, used when the name cant be read this time
    try:
        with open(LAST_PART_FILE) as file:
            part = file.read().strip()
    except OSError:
        return None
    return part if part in charts.INSTRUMENT_NAMES else None

def save_part_picture(shot):
    # what the part line looked like when it could not be read, so the reader can be fixed afterwards
    try:
        image, _ = to_1080(np.ascontiguousarray(shot))
        cv2.imwrite(os.path.join("data", "logs", "ready-screen-part.png"), image[700:1080, 0:430])
    except Exception:
        pass

force_screen_read = threading.Event() # the read-screen hotkey: look at the screen for the song right now

def ready_screen_worker():
    from PIL import ImageGrab
    try:
        reader = ReadyScreenReader()
    except Exception as e:
        log(Fore.RED + f"ERROR: Could not start ready screen reading: {e}" + Fore.RESET)
        return
    automatic = enabled("auto_detect_song")
    last_seen = None
    warned = None
    unclear = 0
    unknown = 0 # looks in a row at a song that is playing and is not the one loaded nor in the list
    sent, sent_at = None, 0.0 # what was last handed to the main loop, so it is not loaded again while that is still switching
    cycle = 0
    timer_cycle = 0
    timer_read = None # (when, seconds left) of the last time the game's song timer could be read
    timer_strikes = 0
    while True:
        forced = force_screen_read.wait(1.0)
        if forced:
            force_screen_read.clear()
        active = current
        chart_now, sync = active[0], active[1]
        # The game shows the time left in the song under its name. With the song length that is where the song is, to
        # within a second. It tells the chart clock which repeat of a riff it is looking at, at the start or in the
        # middle of a song, and it catches a clock that was set to the wrong spot.
        if automatic and sync is not None and not picking and chart_now.get("length"):
            timer_cycle += 1
            if not sync.locked or timer_cycle % 5 == 0:
                read_at, left = time.perf_counter(), None
                try:
                    left = reader.time_left(np.array(ImageGrab.grab(bbox=reader.time_left_box(monitor_width, monitor_height)))[:, :, ::-1])
                except Exception:
                    pass
                before, timer_read = timer_read, ((read_at, left) if left is not None else timer_read)
                # one reading alone is not believed: the one before has to say the same, counted down
                if left is not None and before is not None and read_at - before[0] <= 12 and abs((left + read_at) - (before[1] + before[0])) <= 1.3:
                    position = chart_now["length"] - left + 0.5
                    if not sync.locked:
                        sync.hint_position(read_at, position)
                        timer_strikes = 0
                    else:
                        clock_position = sync.song_time(read_at)
                        timer_strikes = timer_strikes + 1 if abs(clock_position - (position + sync.hint_bias)) > 3.0 else 0
                        if timer_strikes >= 2:
                            timer_strikes = 0
                            log(Fore.YELLOW + f"The game's song timer says {charts.clock(position)} but the chart clock was at {charts.clock(clock_position)}. Syncing again from the timer" + Fore.RESET)
                            sync.unlock(expect=[])
                            sync.hint_position(read_at, position)
        else:
            timer_read, timer_strikes = None, 0
        if not forced and (not automatic or picking or (sync is not None and sync.locked)):
            continue # the chart is playing, only the hotkey looks then
        cycle += 1
        where = "ready screen"
        try:
            ready = forced or reader.header_visible(np.array(ImageGrab.grab(bbox=reader.header_box(monitor_width, monitor_height)))[:, :, ::-1])
            if not ready and cycle % 3:
                continue # no ready screen: every few seconds look at which song is playing instead
            shot = np.array(ImageGrab.grab())[:, :, ::-1]
            seen = reader.read(shot, songs, force=forced) if ready else None
            if seen is None or (forced and not seen["songs"]):
                # while a song plays its name is at the bottom left of the screen
                playing = reader.read_playing(shot, songs)
                if seen is None or playing["songs"]:
                    seen, where = playing, "song that is playing"
        except Exception as e:
            # usually the display being busy for a moment, not a reason to stop reading for the rest of the session
            if warned != "grab" or forced:
                warned = "grab"
                log(Fore.YELLOW + f"Screen reading paused, will try again: {e}" + Fore.RESET)
            if not forced:
                time.sleep(5.0)
            continue
        loaded_now = current[0]
        if forced:
            # always say what was read, that is the point of asking
            if seen["songs"]:
                names = ", ".join(song["name"] for song in seen["songs"])
                log(Fore.CYAN + f"Screen read ({where}): {names}. Part line read as \"{seen['part_text']}\"" + Fore.RESET)
            else:
                save_part_picture(shot)
                log(Fore.YELLOW + "Screen read: no song found. It works on the ready screen (song cards at the top) and while a song plays (its name at the bottom left). A picture of what it looked at is in data/logs" + Fore.RESET)
        if not seen["songs"]:
            stranger = False
            if seen["unmatched"]:
                title, artist = seen["unmatched"][0]
                if where == "ready screen":
                    problem = f"The ready screen shows \"{title}\" / \"{artist}\", which fits no song in the chart list"
                    if warned != problem:
                        warned = problem
                        log(Fore.YELLOW + problem + Fore.RESET)
                else:
                    # a song is playing that is not the one loaded and has no chart: seen twice in a row, the old chart goes
                    stranger = seen["in_song"] and loaded_now is not None and SequenceMatcher(None, fold(title), fold(loaded_now["name"].rpartition(" by ")[0])).ratio() < 0.5
            unknown = unknown + 1 if stranger else 0
            if unknown >= 2:
                unknown = 0
                last_seen = None
                ready_screen_setlists.put(("unload", f"{title} / {artist}"))
            continue
        unknown = 0
        if where != "ready screen" and not forced:
            # the automatic look at the song that is playing only matters when it is not the song that is loaded
            if loaded_now is not None and loaded_now["name"] == seen["songs"][0]["name"] and seen["instrument"] in (None, loaded_now["instrument"]):
                continue
        patient = where == "ready screen" and not forced
        instrument, assumed = seen["instrument"], False
        if instrument is None and not seen["pro"]:
            unclear += 1
            if unclear < 4 and patient:
                continue # the panel is still sliding in
            # still unreadable after a few looks: go with the part from last time rather than not playing at all
            instrument = remembered_part()
            if instrument is None and forced and last_instrument in charts.INSTRUMENT_NAMES:
                instrument = last_instrument
            assumed = instrument is not None
        else:
            unclear = 0
        problem = None
        if seen["pro"]:
            problem = "Pro parts are not supported, pick a normal part to autoplay"
        elif instrument is None:
            problem = f"Could not read your part on the {where} (it read \"{seen['part_text']}\"), press {config['song_select_key']} to pick it"
        elif seen["expert"] is False and not forced:
            problem = "Charts are Expert only, set the difficulty to Expert to autoplay from the chart"
        if problem:
            if warned != problem or forced:
                warned = problem
                log(Fore.YELLOW + problem + Fore.RESET)
                if instrument is None:
                    save_part_picture(shot)
            continue
        warned = None
        if not assumed:
            remember_part(instrument)
        setlist = tuple((song["name"], instrument) for song in seen["songs"])
        if setlist == last_seen and patient and loaded_now is not None and loaded_now["name"] == seen["songs"][0]["name"]:
            continue
        if not forced and setlist == sent and time.perf_counter() - sent_at < 10:
            continue
        last_seen = setlist
        if assumed:
            save_part_picture(shot)
            log(Fore.YELLOW + f"Could not read your part (it read \"{seen['part_text']}\"), using {charts.INSTRUMENT_NAMES[instrument]} like last time. Press {config['song_select_key']} if that is wrong" + Fore.RESET)
        if forced and seen["expert"] is False:
            log(Fore.YELLOW + "The difficulty on screen does not read as Expert. The chart is Expert, so it only fits on Expert" + Fore.RESET)
        if where != "ready screen" and not forced:
            was = f" instead of {loaded_now['name']}" if loaded_now is not None else ""
            log(Fore.CYAN + f"The game is playing {seen['songs'][0]['name']}{was}, loading that" + Fore.RESET)
        loaded = [load_song_chart(song, instrument, say=log) for song in seen["songs"]]
        loaded = [chart for chart in loaded if chart is not None]
        if loaded:
            sent, sent_at = setlist, time.perf_counter()
            ready_screen_setlists.put((loaded, forced or where != "ready screen"))

def finish_screen_recording(save):
    stop_screen_recording()
    if screen_learner is None:
        return
    with screen_learning_lock:
        recording = screen_learner.finish_recording(time.perf_counter())
    if recording is None:
        return
    song, instrument, notes = recording
    if not save:
        log(Fore.YELLOW + f"Screen chart for {song['name']} was not saved because the song did not finish" + Fore.RESET)
        return
    if len(notes) < 6:
        log(Fore.YELLOW + f"Not enough screen notes were detected to save a chart for {song['name']}" + Fore.RESET)
        return
    source_chart = current[0]
    if source_chart is not None and not source_chart.get("learned"):
        notes = charts.restore_source_drums_sustains(notes, source_chart)
        issue = charts.learned_chart_quality({"notes": notes}, source_chart)
        if issue is not None:
            log(Fore.YELLOW + f"Screen-chart backup for {song['name']} was not saved: {issue}. Playback used the source chart; this is not a gameplay miss report." + Fore.RESET)
            return
    try:
        saved = charts.save_learned_chart(song, instrument, notes, source_chart)
    except (OSError, ValueError, TypeError) as e:
        log(Back.RED + Fore.WHITE + f"ERROR: Could not save the learned chart. {str(e)}" + Back.RESET + Fore.RESET)
        return
    if saved:
        log(Fore.GREEN + f"Saved screen-learned chart for {song['name']} ({len(notes)} notes)" + Fore.RESET)
    else:
        log(Fore.YELLOW + f"Kept the more complete saved chart for {song['name']}" + Fore.RESET)

def activate_chart(chart, now=None):
    global current, timing_tuner
    finish_timing_tuner()
    finish_screen_recording(save=False)
    sync = charts.ChartSync(chart, config["chart_sync_tolerance_ms"] / 1000)
    sync.fine_tune = enabled("screen_fine_tune")
    sync.resume(time.perf_counter() if now is None else now)
    actions = build_actions(chart)
    next_current = (chart, sync, actions, [action[0] for action in actions])
    if screen_learner is not None:
        with screen_learning_lock:
            screen_learner.reset(
                recording=not chart.get("learned", False),
                song=chart,
                instrument=chart["instrument"],
            )
            current = next_current
    else:
        current = next_current
    with timing_tuner_lock:
        timing_tuner = TimingTuner(chart_offset * 1000)

    sustains = sum(1 for note in chart["notes"] if note[2] > 0)
    console_print(Fore.GREEN + Style.BRIGHT + f"{chart['name']} - {charts.INSTRUMENT_NAMES[chart['instrument']]} Expert" + Style.RESET_ALL)
    console_print(f"{len(chart['notes'])} notes, {sustains} sustains, {charts.clock(chart['length'] or chart['end'])} long")
    console_print(f"Overdrive path: {chart['path']} ({len(chart['overdrive'])} activations found)")
    # same as the in game timer, so its counting down when theres a song length
    for index, (press_time, window_start, window_end) in enumerate(chart["overdrive"]):
        at = chart["length"] - press_time if chart["length"] else press_time
        console_print(f"  {index + 1}. {charts.clock(at)}  on {chart['overdrive_labels'][index]}")
    if not enabled("use_overdrive"):
        console_print(Fore.YELLOW + "use_overdrive is off, overdrive wont be activated" + Fore.RESET)
    console_print(Fore.YELLOW + "Ready, go to Fortnite and turn caps lock on before the song starts" + Fore.RESET)

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
    if current[0] is None:
        return

    add_queued_songs()

def add_queued_songs():
    while charts.prompt_queue_another():
        chart = load_selected_chart()
        if chart is None:
            break
        queued_charts.append(chart)
        print(Fore.GREEN + f"Added {chart['name']} - {charts.INSTRUMENT_NAMES[chart['instrument']]} to queue ({len(queued_charts)} queued)" + Fore.RESET)

def pick_after_queue_finished():
    global picking
    if ready_screen_on:
        console_print(Fore.CYAN + f"Queue finished. Waiting for the next ready screen, or press {config['song_select_key']} to pick a song." + Fore.RESET)
        return
    picking = True
    try:
        if not charts.prompt_queue_another("Queue finished. Pick another song? (Y/N)"):
            console_print(Fore.YELLOW + f"Queue is empty. Press {config['song_select_key']} later to choose a song." + Fore.RESET)
            return
        chart = load_selected_chart()
        if chart is None:
            console_print(Fore.YELLOW + f"No song selected. Press {config['song_select_key']} later to choose one." + Fore.RESET)
            return
        activate_chart(chart)
        add_queued_songs()
    finally:
        picking = False

def save_offset():
    # write the tuned timing into config.json without touching anything else in it
    with timing_tuner_lock:
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

def finish_timing_tuner():
    global chart_offset, timing_tuner
    with timing_tuner_lock:
        if timing_tuner is None:
            return
        previous_offset = chart_offset
        chart_offset = timing_tuner.finish() / 1000
        timing_tuner = None
        if chart_offset != previous_offset:
            log(Fore.YELLOW + f"Timing check ended before its comparison finished; restored {describe_offset(chart_offset)}" + Fore.RESET)

def record_timing_grade(grade, chart, sync):
    global chart_offset
    with timing_tuner_lock:
        if timing_tuner is None or current[0] is not chart or current[1] is not sync or not autoplaying or picking:
            return
        update = timing_tuner.observe(grade)
        if update is None:
            return
        chart_offset = update["offset_ms"] / 1000
        if update["save"]:
            saved = save_offset()
        else:
            saved = False

        if update["phase"] == "trial":
            timing = describe_offset(chart_offset)
            log(Fore.YELLOW + f"Timing check: trying {timing} for the next {timing_tuner.batch_size} clear grades; a few Goods may happen during this brief test" + Fore.RESET)
        elif update["reason"] == "all_perfect":
            log(Fore.GREEN + f"Timing check: the first {timing_tuner.batch_size} clear grades were all Perfect; keeping {describe_offset(chart_offset)}" + Fore.RESET)
        else:
            outcome = f"{describe_offset(chart_offset)} selected"
            if update["save"]:
                outcome += " and saved" if saved else " (could not save)"
            log(Fore.GREEN + f"Timing check complete: {outcome}" + Fore.RESET)

if use_charts:
    print(Fore.CYAN + Style.BRIGHT + "\nHow it plays" + Style.RESET_ALL)
    if enabled("auto_detect_song"):
        print("  1. Go to the ready screen in Fortnite; Stellite reads the setlist and your part by itself (Expert, no Pro parts)")
    else:
        print("  1. Pick a song and instrument below; answer Y to queue more songs")
    print("  2. Turn Caps Lock on before the song starts and keep it on. Stellite starts by itself on the first notes, no key needed")
    print("  3. After each song, start the next one in Fortnite; Stellite loads its chart and syncs")
    print(Fore.CYAN + Style.BRIGHT + "Hotkeys (they work while Fortnite is open)" + Style.RESET_ALL)
    print(f"  {config['song_select_key']}   Pick a different song. Click this window afterwards to type the name")
    print(f"  {config['sync_key']}   Optional: sync by hand. With Caps Lock on, press when the first note reaches the hit line")
    print(f"  {str.upper(config['restart_key'])}   You restarted the song in game: Stellite drops its sync and syncs again from the start")
    print(f"  {config['read_screen_key']}   Read the song from the screen right now: on the ready screen, or while a song is playing")
    print(f"  {config['nudge_earlier_key']}   Play notes {config['chart_nudge_step_ms']} ms earlier. Press it while playing if you get Goods instead of Perfects")
    print(f"  {config['nudge_later_key']}   Play notes {config['chart_nudge_step_ms']} ms later, if you went too far")
    print(f"  {str.upper(config['exit_key'])}   Exit")
    print(f"Timing: notes play {describe_offset(chart_offset)}. Change it with {config['nudge_earlier_key']} and {config['nudge_later_key']} while playing, it saves by itself")
    if overdrive_offset:
        print(f"Overdrive plays another {describe_offset(overdrive_offset)} than the notes (overdrive_timing_offset_ms)")
    if enabled("auto_detect_song"):
        print(Fore.CYAN + f"Waiting for the ready screen. Press {config['song_select_key']} to pick a song by hand instead" + Fore.RESET)
    else:
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
screen_center = monitor_width // 2
grade_left = screen_center - int(550 / scale_factor)
grade_right = screen_center - int(320 / scale_factor)
grade_top = int(840 / scale_factor)
grade_bottom = int(910 / scale_factor)
combo_left = screen_center - int(440 / scale_factor)
combo_right = screen_center - int(350 / scale_factor)
combo_top = int(790 / scale_factor)
combo_bottom = int(840 / scale_factor)
capture_left = min(region_fromleft, grade_left, combo_left)
capture_top = region_fromtop
capture_right = region_fromleft + region_width
capture_bottom = max(region_fromtop + region_height, grade_bottom, combo_bottom)
note_region_x = region_fromleft - capture_left
grade_region = (grade_left - capture_left, grade_top - capture_top, grade_right - capture_left, grade_bottom - capture_top)
combo_region = (combo_left - capture_left, combo_top - capture_top, combo_right - capture_left, combo_bottom - capture_top)
emote_prompt_region = (
    int(monitor_width * 0.42) - capture_left,
    int(monitor_height * 0.66) - capture_top,
    int(monitor_width * 0.58) - capture_left,
    int(monitor_height * 0.79) - capture_top,
)
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

hold_template = load_template("hold")
if hold_template is not None:
    templates.append((hold_template, config["screen_learning_confidence"], True))
else:
    print(Fore.YELLOW + "No hold match image found; sustain learning will use screen pixels only" + Fore.RESET)

screen_learner = ScreenChartLearner(number_of_lanes, section_size, min_tile_pixels_top_offset)
if current[0] is not None:
    screen_learner.reset(
        recording=not current[0].get("learned", False),
        song=current[0],
        instrument=current[0]["instrument"],
    )

capture_region = (capture_left, capture_top, capture_right, capture_bottom)
# the region goes to create() as well, bettercam sizes its frame buffer from it whenever capture has to be set up again
main_camera = bettercam.create(output_color = "GRAY", max_buffer_len=64, region=capture_region)

# When Windows takes screen capture away (display mode change, driver hiccup) bettercam sets it up again as fast as it can,
# forever. On this PC every new capture made the NVIDIA driver reset a few seconds later, so that loop kept the whole screen
# black until python was killed. Capture is therefore set up again calmly and only a couple of times per session. After that
# it stays off and the bot says so instead of fighting the display.
CAPTURE_RECOVERIES = 2 # times per session capture may be set up again
CAPTURE_RECOVERY_PAUSE = 3.0 # seconds to leave the display alone first
capture_recoveries = 0
capture_lost = None # why capture is off for good, None while it is fine

def give_up_capture(reason):
    global capture_lost
    capture_lost = reason
    try:
        main_camera._BetterCam__stop_capture.set() # bettercam's capture thread then ends by itself
    except AttributeError:
        raise RuntimeError(reason) # some other bettercam version, end its thread the hard way

def recover_capture():
    # stands in for bettercam's own _on_output_change, which retries in a tight loop without ever giving up
    global capture_recoveries
    if capture_lost is not None:
        return
    if capture_recoveries >= CAPTURE_RECOVERIES:
        give_up_capture("Windows keeps taking screen capture away")
        return
    capture_recoveries += 1
    time.sleep(CAPTURE_RECOVERY_PAUSE)
    try:
        camera = main_camera
        camera._duplicator.release()
        camera._stagesurf.release()
        camera._output.update_desc()
        camera.width, camera.height = camera._output.resolution
        camera._validate_region(camera.region)
        camera._rebuild_frame_buffer(camera.region)
        camera.rotation_angle = camera._output.rotation_angle
        camera._stagesurf.rebuild(output=camera._output, device=camera._device)
        camera._duplicator = type(camera._duplicator)(output=camera._output, device=camera._device)
    except Exception as e:
        give_up_capture(f"screen capture could not be set up again ({e})")

main_camera._on_output_change = recover_capture
main_camera.start(region=capture_region, target_fps=config["capture_fps"])

def capture_alive():
    return any(thread.name == "BetterCam" and thread.is_alive() for thread in threading.enumerate())

running = True
autoplaying = caps_lock()

lane_busy = [False] * number_of_lanes
lane_lock = threading.Lock()
lane_last_seen = [0.0] * 5
sighting_lock = threading.Lock()
manual_key_logger = ManualKeyLogger(
    [*lane_keys, overdrive_key, "b"],
    lambda: not caps_lock() and not picking,
    lambda message: log(Fore.BLUE + message + Fore.RESET),
)
keyboard.hook(manual_key_logger.handle)
threading.Thread(target=lane_status_worker, daemon=True).start()
start_lane_status()

def truncate(n, decimals = 0):
    multiplier = 10 ** decimals
    return int(n * multiplier) / multiplier

def press_lane_key(lane):
    keyboard.press(lane_keys[lane])
    with lane_state_lock:
        changed = not lane_key_down[lane]
        lane_key_down[lane] = True
        if changed:
            lane_status_changed.set()

def release_lane_key(lane):
    keyboard.release(lane_keys[lane])
    with lane_state_lock:
        changed = lane_key_down[lane]
        lane_key_down[lane] = False
        if changed:
            lane_status_changed.set()

def press_overdrive_key():
    global overdrive_key_down
    keyboard.press(overdrive_key)
    with lane_state_lock:
        changed = not overdrive_key_down
        overdrive_key_down = True
        if changed:
            lane_status_changed.set()

def release_overdrive_key():
    global overdrive_key_down
    keyboard.release(overdrive_key)
    with lane_state_lock:
        changed = overdrive_key_down
        overdrive_key_down = False
        if changed:
            lane_status_changed.set()

def press(lane):
    key = lane_keys[lane]
    log(Fore.GREEN + f"{time.time()}: Pressing {str.capitalize(key)}" + Fore.RESET)
    press_lane_key(lane)
    time.sleep(config["keypress_holdtime"])
    release_lane_key(lane)
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
        record_sighting(frame_time, lane, sync)
        expected_lanes = sync.add_sighting(frame_time, lane, chart_offset)
        if expected_lanes:
            expected_keys = ", ".join(str.capitalize(lane_keys[index]) for index in expected_lanes)
            log(Fore.RED + Style.BRIGHT + f"{time.time()}: Possible wrong note: detected {str.capitalize(lane_keys[lane])}, chart expects {expected_keys}" + Style.RESET_ALL)

def press_tiles(events, frame_time):
    sync = current[1]
    from_chart = sync is not None and sync.locked
    for lane, center_x, center_y, screen_pressable in events:
        tile_seen(lane, frame_time)
        if autoplaying and not picking and not from_chart and screen_pressable:
            press_tile(lane)
        if enabled("debug_positions"):
            log(f"Found tile in lane {str.capitalize(lane_keys[lane])} at ({center_x}, {center_y})")

def tile_logic(screenshot_np, frame_time):
    with screen_learning_lock:
        active_chart = current
        recording = screen_learner.recording
    chart = active_chart[0]
    learning_mode = recording or bool(chart and chart.get("learned"))
    rectangles = []
    confidences = []
    hold_hints = []
    hold_anchors = []
    press_thresholds = []
    nms_threshold = float("inf")

    for template_data in templates:
        template, default_confidence = template_data[:2]
        hold_hint = len(template_data) == 3 and template_data[2]
        if hold_hint and not learning_mode:
            continue
        min_confidence = config["screen_learning_confidence"] if learning_mode else default_confidence
        nms_threshold = min(nms_threshold, min_confidence)
        # hold.png contains the head lower in its image than the tile template does.
        anchor_offset = int(template.shape[0] * 0.55) if hold_hint else template.shape[0] // 2
        crop_top = max(0, min(min_tile_pixels_top_offset - anchor_offset - 4, region_height - template.shape[0]))
        results = cv2.matchTemplate(screenshot_np[crop_top:], template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(results >= min_confidence)
        for y, x in zip(*locations):
            rectangle = (int(x), int(y) + crop_top, int(template.shape[1]), int(template.shape[0]))
            rectangles.append(rectangle)
            confidences.append(float(results[y, x]))
            hold_hints.append(hold_hint)
            press_thresholds.append(default_confidence)
            hold_anchors.append(
                (rectangle[0] + rectangle[2] // 2, rectangle[1] + anchor_offset)
                if hold_hint else None
            )

    if rectangles:
        kept = cv2.dnn.NMSBoxes(rectangles, confidences, nms_threshold, 0.2)
        indices = np.asarray(kept).reshape(-1)
        detections = []
        for index in indices:
            x, y, width, height = rectangles[index]
            anchor_y = y + (int(height * 0.55) if hold_hints[index] else height // 2)
            anchor_x = x + width // 2
            hold_hint = hold_hints[index] or any(
                abs(anchor_x - hold_x) <= 18 and abs(anchor_y - hold_y) <= 18
                for other, hold_anchor in enumerate(hold_anchors)
                if other != index and hold_anchor is not None
                for hold_x, hold_y in (hold_anchor,)
            )
            detections.append((
                x, y, width, height, confidences[index], hold_hint,
                anchor_y, not hold_hints[index] and confidences[index] >= press_thresholds[index],
            ))
    else:
        detections = []

    with screen_learning_lock:
        if current is not active_chart:
            return
        events = screen_learner.process_frame(screenshot_np, detections, frame_time)
        press_tiles(events, frame_time)

# Capture and detection threads
# Match every template against the same newest frame so nothing piles up.
frame_condition = threading.Condition()
latest_frame = None
latest_frame_time = 0.0
frame_number = 0

def capture_loop():
    global latest_frame, latest_frame_time, frame_number
    frame_shape = (capture_region[3] - capture_region[1], capture_region[2] - capture_region[0])
    while running:
        try:
            screenshot_np = main_camera.get_latest_frame()
        except Exception:
            time.sleep(0.05) # capture is being restarted
            continue
        frame_time = time.perf_counter()
        if screenshot_np is None or screenshot_np.shape[:2] != frame_shape:
            continue
        with frame_condition:
            latest_frame = screenshot_np
            latest_frame_time = frame_time
            frame_number += 1
            frame_condition.notify_all()

def detection_worker():
    seen = 0
    while running:
        with frame_condition:
            if frame_number == seen:
                frame_condition.wait(0.1)
            if frame_number == seen:
                continue
            screenshot_np, frame_time, seen = latest_frame, latest_frame_time, frame_number
        with screen_learning_lock:
            recording = screen_learner.recording
        if not picking and (autoplaying or recording):
            note_frame = screenshot_np[:region_height, note_region_x:note_region_x + region_width]
            tile_logic(note_frame, frame_time)

def grade_worker():
    try:
        reader = VisualGradeReader()
        emote_reader = EmotePromptReader(reader.ocr)
    except Exception as e:
        log(Fore.RED + f"ERROR: Could not start local hit-grade recognition: {e}" + Fore.RESET)
        return

    seen = 0
    tracked_chart = None
    last_sample_time = 0.0
    last_emote_check = 0.0
    while running:
        with frame_condition:
            if frame_number == seen:
                frame_condition.wait(0.1)
            if frame_number == seen:
                continue
            screenshot_np, seen = latest_frame, frame_number

        now = time.perf_counter()
        if now - last_sample_time < 0.1:
            continue
        last_sample_time = now

        chart, sync, _, _ = current
        if chart is not tracked_chart:
            reader.reset()
            tracked_chart = chart
        if not autoplaying or picking:
            reader.reset()
            emote_reader.reset()
            continue

        try:
            # the prompt check is a full text search of that area (about 0.3 s), twice a second leaves the grades their turn
            emote_seen = False
            if now - last_emote_check >= 0.5:
                last_emote_check = now
                emote_seen = emote_reader.observe(screenshot_np, emote_prompt_region, now)
            if emote_seen:
                keyboard.press("b")
                try:
                    time.sleep(0.05)
                finally:
                    keyboard.release("b")
                log(Fore.CYAN + f"{time.time()}: Tapped B for on-screen GESTO prompt" + Fore.RESET)

            if chart is None or sync is None or not sync.locked:
                reader.reset()
                continue
            with timing_tuner_lock:
                active = timing_tuner is not None and not timing_tuner.finished
            if not active:
                reader.reset()
                continue
            grade = reader.observe(screenshot_np, grade_region, combo_region)
        except Exception as e:
            log(Fore.RED + f"ERROR: Local screen prompt and hit-grade recognition stopped: {e}" + Fore.RESET)
            return
        if grade and current[0] is chart and current[1] is sync and autoplaying and not picking:
            record_timing_grade(grade, chart, sync)

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
                release_lane_key(lane)
            held.clear()
            if overdrive_held:
                release_overdrive_key()
                overdrive_held = False
            if sync is None or not sync.locked or not autoplaying or picking:
                following = None
                time.sleep(0.005)
                continue
            following = (sync, sync.version)
            index = bisect.bisect_left(action_times, sync.song_time(time.perf_counter()) - chart_offset + 0.005)
            with sync.mutex:
                first_note_lanes = tuple(sync.initial_press_lanes)
            for lane in first_note_lanes:
                press_lane_key(lane)
                held.add(lane)
                log(Fore.GREEN + f"{time.time()}: Pressing {str.capitalize(lane_keys[lane])} (first note, manual sync)" + Fore.RESET)

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

        if kind in ("press", "hold"):
            # way too late is a miss anyway, dont press into the next note
            if late < 0.05:
                press_lane_key(lane)
                held.add(lane)
                action = "Holding" if kind == "hold" else "Pressing"
                log(Fore.GREEN + f"{time.time()}: {action} {str.capitalize(lane_keys[lane])} (chart)" + Fore.RESET)
            else:
                log(Fore.RED + format_skipped_key(lane_keys[lane], late) + Fore.RESET)
        elif kind in ("release", "lift"):
            if lane in held:
                release_lane_key(lane)
                held.discard(lane)
                if kind == "lift":
                    # this release is itself a note: the key was held from the note before and let go right on this one
                    log(Fore.GREEN + f"{time.time()}: Releasing {str.capitalize(lane_keys[lane])} (chart, lift note)" + Fore.RESET)
        elif kind == "overdrive":
            if late < 0.1:
                press_overdrive_key()
                overdrive_held = True
                log(Fore.MAGENTA + Style.BRIGHT + f"{time.time()}: Activating overdrive" + Style.RESET_ALL)
        elif kind == "overdrive_release":
            if overdrive_held:
                release_overdrive_key()
                overdrive_held = False
        index += 1

threading.Thread(target=capture_loop, daemon=True).start()
threading.Thread(target=detection_worker, daemon=True).start()
ready_screen_on = use_charts and enabled("auto_detect_song")
if use_charts:
    threading.Thread(target=grade_worker, daemon=True, name="stellite-grade-reader").start()
    threading.Thread(target=chart_player, daemon=True).start()
    # runs with auto_detect_song off too, then it only looks at the screen when the read-screen key is pressed
    threading.Thread(target=ready_screen_worker, daemon=True, name="stellite-ready-screen").start()

overlay = None
if use_charts and enabled("show_overlay"):
    try:
        overlay = Overlay()
        overlay.set_clickthrough(autoplaying)
    except Exception as e:
        print(Fore.YELLOW + f"Could not open the overlay: {str(e)}" + Fore.RESET)
        overlay = None

def overlay_title():
    chart = current[0]
    if chart is None:
        return "No song loaded"
    more = f"  (+{len(queued_charts)} queued)" if queued_charts else ""
    return f"{chart['name']}  -  {charts.INSTRUMENT_NAMES[chart['instrument']]}{more}"

def overlay_text(now):
    if capture_lost is not None:
        return ("-:--", "SCREEN CAPTURE OFF restart Stellite", "#ff5a65", "dim")
    chart, sync, actions, action_times = current
    if sync is None:
        status = f"Press {config['song_select_key']} to pick a song" if autoplaying else "Caps Lock OFF - autoplay paused"
        return ("-:--", status, "dim", "dim")
    # festival style song timer, counts down from the song length like the one in game
    length = chart["length"]
    if not sync.locked:
        small = "Waiting for the first notes, starts by itself" if autoplaying else "Caps Lock OFF - autoplay paused"
        return (charts.clock(length) if length else "-:--", small, "dim", "white" if length else "dim")
    song_time = sync.song_time(now)
    timer = charts.clock(length - song_time) if length else "-:--"
    if not autoplaying:
        return (timer, "Caps Lock OFF - chart keys are not being sent", "dim", "white")
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

def overlay_highway(now):
    chart, sync, actions, action_times = current
    status = "SYNCING"
    notes = []
    held = []
    if sync is None:
        status = "NO SONG"
    elif not sync.locked:
        status = "SYNCING" if autoplaying else "CAPS OFF"
    elif not autoplaying or picking:
        status = "CAPS OFF"
    else:
        status = "LIVE"
        song_time = sync.song_time(now)
        overdrive_notes = set(chart.get("overdrive_notes", ()))
        first_action = bisect.bisect_left(action_times, song_time - chart_offset - 0.05)
        for action_time, _, kind, lane in actions[first_action:]:
            eta = sync.wall_time(action_time) + chart_offset - now
            if eta > 2.5:
                break
            if kind in ("press", "hold", "lift") and lane is not None and eta >= -0.05:
                marker = "overdrive" if (action_time, lane) in overdrive_notes else kind
                notes.append((lane, max(0.0, eta), marker))
        with lane_state_lock:
            held = [lane for lane, is_down in enumerate(lane_key_down) if is_down]
    return {"lanes": lane_keys, "notes": notes, "held": held, "status": status}

overlay_note = ("", 0.0) # short message that covers the bottom line for a bit

hotkeys_down = {}
def fortnite_focused():
    # letter hotkeys only count in game, otherwise typing anywhere else would trigger them
    try:
        return "fortnite" in win32gui.GetWindowText(win32gui.GetForegroundWindow()).lower()
    except Exception:
        return False

def hotkey(key):
    # true once per key press, not every loop while its held
    pressed = keyboard.is_pressed(key)
    was_pressed = hotkeys_down.get(key, False)
    hotkeys_down[key] = pressed
    return pressed and not was_pressed

last_overlay = 0.0
sync_logged = (None, None) # sync object and clock offset last written to the log
last_sync_check = 0.0
OVERLAY_FRAME = 1 / 120 # overlay panel refresh, 120 fps
synced_before = False
last_capture_check = 0.0
capture_lost_reported = False
try:
    while not keyboard.is_pressed(config['exit_key']):
        now = time.perf_counter()
        if now - last_capture_check >= 2.0:
            last_capture_check = now
            if capture_lost is None and not capture_alive():
                capture_lost = "the capture thread stopped"
            if capture_lost is not None and not capture_lost_reported:
                # said once, loudly. capture is never started again by itself, see recover_capture
                capture_lost_reported = True
                log(Fore.RED + Style.BRIGHT + f"SCREEN CAPTURE IS OFF: {capture_lost}. Stellite cannot see the game and will not play. Close it with {str.upper(config['exit_key'])}, make sure Fortnite is in Windowed Fullscreen, then start it again." + Style.RESET_ALL)
        capslock_status = caps_lock()
        if capslock_status != autoplaying:
            autoplaying = capslock_status
            if current[1] is not None and autoplaying:
                current[1].resume(now)
            if autoplaying:
                if current[1] is not None and current[1].locked:
                    song_time = current[1].song_time(now)
                    log(Fore.YELLOW + f"Autoplay ON at {charts.clock(song_time)}. Earlier chart notes were skipped while Caps Lock was off." + Fore.RESET)
                else:
                    log(Fore.GREEN + "Autoplay ON; waiting for chart sync." + Fore.RESET)
            else:
                log(Fore.YELLOW + "Autoplay OFF. Caps Lock is off; chart keys will not be sent." + Fore.RESET)
            if overlay is not None:
                overlay.set_clickthrough(autoplaying)

        chart, sync, actions, action_times = current
        if sync is not None:
            if sync.try_lock(now):
                start_screen_recording(chart)
                if autoplaying:
                    log(Fore.GREEN + Style.BRIGHT + f"Synced to {chart['name']} at {charts.clock(sync.song_time(now))}, playing from the chart" + Style.RESET_ALL)
                else:
                    log(Fore.RED + Style.BRIGHT + f"Synced to {chart['name']} at {charts.clock(sync.song_time(now))}, but CAPS LOCK IS OFF so nothing is being pressed. Turn Caps Lock on" + Style.RESET_ALL)
                if not synced_before:
                    synced_before = True
                    log(Fore.CYAN + f"If clear Goods appear, Stellite will test nearby timing; press {config['nudge_earlier_key']} or {config['nudge_later_key']} to adjust manually" + Fore.RESET)
            message = sync.check(now, autoplaying)
            if message:
                log(Fore.YELLOW + f"{message}, reading the screen until it syncs again" + Fore.RESET)
                if message == "Song finished":
                    finish_screen_recording(save=True)
                    finish_timing_tuner()
                if message == "Song finished" and queued_charts:
                    next_chart = queued_charts.pop(0)
                    activate_chart(next_chart, now)
                    chart, sync, actions, action_times = current
                    log(Fore.CYAN + f"Starting next queued song: {chart['name']} ({len(queued_charts)} remaining)" + Fore.RESET)
                elif message == "Song finished":
                    pick_after_queue_finished()
                    chart, sync, actions, action_times = current

        try:
            setlist, asked_for = ready_screen_setlists.get_nowait()
        except queue.Empty:
            setlist, asked_for = None, False
        if setlist == "unload":
            # the game is playing a song there is no chart for: the chart of another song must not stay loaded
            if not picking and current[0] is not None and not (current[1] is not None and current[1].locked):
                finish_timing_tuner()
                finish_screen_recording(save=False)
                log(Fore.YELLOW + f"The game is playing \"{asked_for}\", not {current[0]['name']}, and there is no chart for it. Playing from the screen only" + Fore.RESET)
                current = (None, None, [], [])
                queued_charts.clear()
                chart, sync, actions, action_times = current
            setlist = None
        # a read that was asked for with the hotkey goes through even mid song, and starts the sync over
        if setlist and not picking and (asked_for or not (current[1] is not None and current[1].locked)):
            same = current[0] is not None and (current[0]["name"], current[0]["instrument"]) == (setlist[0]["name"], setlist[0]["instrument"])
            if asked_for or not same:
                if asked_for:
                    for lane in range(len(lane_keys)):
                        release_lane_key(lane)
                activate_chart(setlist[0], now)
            queued_charts[:] = setlist[1:]
            chart, sync, actions, action_times = current
            names = ", ".join(f"{index + 1}. {item['name']}" for index, item in enumerate(setlist))
            log(Fore.GREEN + Style.BRIGHT + f"{'Screen read' if asked_for else 'Ready screen'}: {charts.INSTRUMENT_NAMES[setlist[0]['instrument']]} Expert - {names}" + Style.RESET_ALL)
            overlay_note = ("song read from screen", now + 2.0)

        # debug: log every time the screen reader moves the chart clock, so drift can be traced afterwards
        if sync is not None and sync.locked:
            offset, drift, _ = sync.model
            if sync_logged[0] is not sync:
                sync_logged = (sync, offset)
                placed = {"start": "the song start", "timer": "the game's song timer", "notes": "the notes alone", "key": "the sync key"}.get(sync.locked_by, "?")
                log(f"{time.time()}: Sync clock set (offset {offset:.3f}, fine tune {'on' if sync.fine_tune else 'off'}, placed by {placed})")
            elif abs(offset - sync_logged[1]) >= 0.01:
                log(Fore.MAGENTA + f"{time.time()}: Sync clock moved {(offset - sync_logged[1]) * 1000:+.0f} ms (drift {drift * 1000:+.1f} ms/s) at {charts.clock(sync.song_time(now))}" + Fore.RESET)
                sync_logged = (sync, offset)
            if now - last_sync_check >= 5:
                # plus means the notes reached the screen later than the chart clock expected
                error_ms, seen = sync.check_summary(now - 5)
                if seen:
                    log(f"{time.time()}: Sync check at {charts.clock(sync.song_time(now))}: screen notes {error_ms:+.0f} ms from the chart ({seen} notes)")
                last_sync_check = now

        if use_charts and hotkey(config["song_select_key"]):
            stop_lane_status()
            picking = True
            print(Fore.MAGENTA + Style.BRIGHT + "\nClick this window to type the song name (autoplay is paused until you pick)" + Style.RESET_ALL)
            pick_song()
            picking = False
            start_lane_status()
            if current[1] is not None:
                current[1].resume(time.perf_counter())
        if use_charts and hotkey(config["read_screen_key"]) and fortnite_focused():
            # look at the screen for the song right now: the ready screen, or the name shown while it plays
            force_screen_read.set()
            log(Fore.CYAN + "Reading the song from the screen..." + Fore.RESET)
            overlay_note = ("reading the screen", now + 2.0)
        if chart is not None and hotkey(config["restart_key"]) and fortnite_focused():
            # the song was restarted in game, throw away the chart clock and sync again from the first note
            for lane in range(len(lane_keys)):
                release_lane_key(lane)
            activate_chart(chart, now)
            chart, sync, actions, action_times = current
            log(Fore.CYAN + f"Song restarted: waiting for {chart['name']} to sync again from the start" + Fore.RESET)
            overlay_note = ("restarted, syncing", now + 2.0)
        if sync is not None and hotkey(config["sync_key"]):
            if sync.locked:
                if sync.manual:
                    log(Fore.YELLOW + f"Already synced; {config['sync_key']} will not hit the first note again" + Fore.RESET)
                else:
                    log(Fore.YELLOW + f"Already synced from the screen, {config['sync_key']} isnt needed" + Fore.RESET)
                overlay_note = ("already synced", now + 1.5)
            elif not autoplaying:
                log(Fore.RED + f"Caps Lock OFF: turn it on before pressing {config['sync_key']} at the first note. Nothing was synced or played." + Fore.RESET)
                overlay_note = ("turn Caps Lock on first", now + 1.5)
            elif not chart["notes"]:
                log(Fore.YELLOW + f"Cannot sync on the first note; {chart['name']} has no chart notes" + Fore.RESET)
                overlay_note = ("chart has no notes", now + 1.5)
            elif (sync.hinted_position(now) or 0.0) > min(note[0] for note in chart["notes"]) + 1.5:
                # the key means "the first note is on the line right now". Pressed later it used to set the clock seconds
                # off and play wrong notes until sync was lost
                log(Fore.YELLOW + f"{config['sync_key']} is for the very first note, and the game's song timer says the song is already at {charts.clock(sync.hinted_position(now))}. Nothing changed, the chart syncs by itself on the next notes" + Fore.RESET)
                overlay_note = ("syncing by itself", now + 1.5)
            else:
                first_note_time = min(note[0] for note in chart["notes"])
                first_lanes = sorted({
                    lane for note_time, lane, _ in chart["notes"]
                    if abs(note_time - first_note_time) < 1e-6
                })
                sync_time = time.perf_counter()
                sync.start_at(sync_time - chart_offset, first_note_time, first_lanes)
                start_screen_recording(chart)
                keys = ", ".join(str.capitalize(lane_keys[lane]) for lane in first_lanes)
                log(Fore.GREEN + Style.BRIGHT + f"First note sync armed ({keys}); Stellite will hit it now. The screen reader will fine-tune timing as more notes appear." + Style.RESET_ALL)
                overlay_note = ("first note sync", sync_time + 1.5)
        for key, step in ((config["nudge_earlier_key"], -1), (config["nudge_later_key"], 1)):
            if use_charts and hotkey(key):
                finish_timing_tuner()
                with timing_tuner_lock:
                    chart_offset += step * config["chart_nudge_step_ms"] / 1000
                    saved = save_offset()
                    timing = describe_offset(chart_offset)
                log(Fore.CYAN + f"Notes now play {timing}" + (f" (saved, chart_timing_offset_ms is {round(chart_offset * 1000, 1):g})" if saved else "") + Fore.RESET)
                overlay_note = (f"notes {timing}", now + 1.5)

        if overlay is not None and now >= last_overlay + OVERLAY_FRAME:
            # step on a fixed 120 fps grid so the loop sleep does not drag the rate down
            last_overlay = last_overlay + OVERLAY_FRAME if now - last_overlay < 2 * OVERLAY_FRAME else now
            big, small, color, big_color = overlay_text(now)
            if now < overlay_note[1]:
                small, color = overlay_note[0], "good"
            overlay.show(big, small, color, big_color, highway=overlay_highway(now), title=overlay_title())
        if overlay is not None:
            # wake up in time for the next overlay frame
            time.sleep(min(0.005, max(0.001, last_overlay + OVERLAY_FRAME - time.perf_counter())))
        else:
            time.sleep(0.005)
except KeyboardInterrupt:
    pass

# STOP
finish_timing_tuner()
running = False
stop_screen_recording()
for lane in range(number_of_lanes):
    release_lane_key(lane)
release_overdrive_key()
keyboard.release("b")
stop_lane_status()
main_camera.stop()
with sightings_lock:
    if sightings_file is not None:
        sightings_file.close()
if overlay is not None:
    overlay.close()
if hwnd:
    win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
ctypes.windll.winmm.timeEndPeriod(1)

log_queue.join()
console_print(Fore.WHITE + Back.RED + "Stop key pressed. Exiting Stellite..." + Fore.RESET + Back.RESET)
