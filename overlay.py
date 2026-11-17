# Stellite overlay
# Click through song clock and overdrive countdown that never steals focus from Fortnite
# Based on the Festival OD Coach overlay by Aknownthreat, made for the Stellite project (GPL-3.0)

import os
import gc
import json
import queue
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
import win32api
import win32con
import win32gui

TRANSPARENT = "#ff00ff" # this color gets cut out of the window
COLORS = {
    "white": "#ffffff",
    "dim": "#c8c8d0",
    "accent": "#f5c542",
    "now": "#ffe566",
    "good": "#7dff9a",
}
LANE_COLORS = ("#46d369", "#ff5a65", "#ffd24a", "#4f9cff", "#ff9d45")
OVERDRIVE_COLOR = "#ffffff"
POSITION_FILE = os.path.join("data", "overlay.json")
FONT_CHOICES = ("Ubuntu", "Bahnschrift", "Segoe UI") # first one that is installed wins
FONT = "Segoe UI"
CAPS_OFF_TEXT = "CAPS LOCK OFF\nnot playing\n(drag to move)"
TOPMOST_SECONDS = 0.25 # how often the panel is pushed back above everything else
TITLE_HEIGHT = 24 # the bar across the top with the song that is loaded

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

def load_position(width, height):
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)
    try:
        with open(POSITION_FILE, "r") as file:
            position = json.load(file)
        x = max(0, min(screen_width - width, int(position["x"])))
        y = max(0, min(screen_height - height, int(position["y"])))
        return x, y
    except Exception:
        return 24, max(24, (screen_height - height) // 2)

def save_position(x, y):
    try:
        os.makedirs("data", exist_ok=True)
        with open(POSITION_FILE, "w") as file:
            json.dump({"x": x, "y": y}, file)
    except Exception:
        pass

def apply_style(hwnd, clickthrough):
    style = win32gui.GetWindowLong(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | win32con.WS_EX_TOPMOST
    if clickthrough:
        style |= WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT
    win32gui.SetWindowLong(hwnd, GWL_EXSTYLE, style)
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

class Overlay:
    # click through while caps lock is on, drag it around while caps lock is off
    def __init__(self):
        self.updates = queue.Queue(maxsize=8)
        self.closed = False
        self.hwnd = None
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name="stellite-overlay")
        self.thread.start()
        self.ready.wait(timeout=3.0)

    def send(self, update):
        if self.closed:
            return
        # only the newest update matters, throw away old ones if tk is behind
        while self.updates.full():
            try:
                self.updates.get_nowait()
            except queue.Empty:
                break
        try:
            self.updates.put_nowait(update)
        except queue.Full:
            pass

    def show(self, big, small, color = "dim", big_color = "white", highway=None, title=""):
        self.send(("text", big, small, color, big_color, highway, title))

    def set_clickthrough(self, enabled):
        self.send(("clickthrough", bool(enabled)))

    def close(self):
        self.closed = True
        self.thread.join(timeout=1.0)

    def run(self):
        root = tk.Tk()
        root.withdraw()
        root.title("Stellite Overlay")
        root.overrideredirect(True)
        root.configure(bg=TRANSPARENT)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", TRANSPARENT)

        width, height = 356, 286 + TITLE_HEIGHT
        x, y = load_position(width, height)
        root.geometry(f"{width}x{height}+{x}+{y}")

        global FONT
        installed = set(tkfont.families())
        FONT = next((family for family in FONT_CHOICES if family in installed), "Segoe UI")
        big_font = tkfont.Font(family=FONT, size=22, weight="bold")
        small_font = tkfont.Font(family=FONT, size=9, weight="bold")
        title_font = tkfont.Font(family=FONT, size=9, weight="bold")

        # the song that is loaded, across the top like a window title
        title_bar = tk.Frame(root, bg="#0c0f15", height=TITLE_HEIGHT, highlightthickness=1, highlightbackground="#394252")
        title_bar.pack(side="top", fill="x")
        title_bar.pack_propagate(False)
        title = tk.Label(title_bar, text="Stellite", font=title_font, fg=COLORS["white"], bg="#0c0f15", anchor="w")
        title.pack(side="left", fill="both", expand=True, padx=8)

        shell = tk.Frame(root, bg=TRANSPARENT)
        shell.pack(fill="both", expand=True)
        highway = tk.Canvas(
            shell,
            width=242,
            height=286,
            bg="#131720",
            highlightthickness=1,
            highlightbackground="#394252",
        )
        highway.pack(side="left", fill="y")
        info = tk.Frame(shell, bg="#131720", width=114, height=286)
        info.pack(side="left", fill="both", expand=True)
        info.pack_propagate(False)
        big = tk.Label(info, text="-:--", font=big_font, fg=COLORS["dim"], bg="#131720")
        big.pack(anchor="center", pady=(88, 0))
        small = tk.Label(info, text="Stellite", font=small_font, fg=COLORS["dim"], bg="#131720", wraplength=104, justify="center")
        small.pack(anchor="center", pady=(8, 0))

        drag = {"x": 0, "y": 0}
        clickthrough = {"on": True}

        def start_drag(event):
            if not clickthrough["on"]:
                drag["x"] = event.x_root - root.winfo_x()
                drag["y"] = event.y_root - root.winfo_y()

        def on_drag(event):
            if not clickthrough["on"]:
                root.geometry(f"+{event.x_root - drag['x']}+{event.y_root - drag['y']}")

        def end_drag(event):
            if not clickthrough["on"]:
                save_position(root.winfo_x(), root.winfo_y())

        for widget in (root, title_bar, title, shell, highway, info, big, small):
            widget.bind("<ButtonPress-1>", start_drag)
            widget.bind("<B1-Motion>", on_drag)
            widget.bind("<ButtonRelease-1>", end_drag)

        root.deiconify()
        root.update_idletasks()
        hwnd = int(root.winfo_id())
        parent = win32gui.GetParent(hwnd)
        if parent:
            hwnd = parent
        self.hwnd = hwnd
        apply_style(hwnd, True)
        self.ready.set()

        last_topmost = 0.0
        shown = None

        # no timer polling here, the loop wakes up the moment the bot sends a frame
        while not self.closed:
            try:
                update = self.updates.get(timeout=0.01)
            except queue.Empty:
                update = None
            # drain everything, but only draw the newest frame
            frame = None
            while update is not None:
                if update[0] == "clickthrough":
                    clickthrough["on"] = update[1]
                    apply_style(hwnd, update[1])
                    shown = None
                else:
                    frame = update
                try:
                    update = self.updates.get_nowait()
                except queue.Empty:
                    update = None
            if frame is not None:
                state = (frame[1:5], frame[6] if len(frame) > 6 else "")
                if state != shown:
                    shown = state
                    title.configure(text=fit_text(state[1] or "Stellite", title_font, width - 20))
                    big.configure(text=frame[1], fg=COLORS.get(frame[4], frame[4]))
                    small.configure(text=frame[2] if clickthrough["on"] else CAPS_OFF_TEXT, fg=COLORS.get(frame[3], frame[3]) if clickthrough["on"] else "#ff5a65")
                draw_highway(highway, frame[5])

            # fortnite likes to cover it up, keep putting it back on top
            now = time.perf_counter()
            if now - last_topmost >= TOPMOST_SECONDS:
                last_topmost = now
                try:
                    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
                except Exception:
                    pass
            root.update()
        root.destroy()
        # tk has to be cleaned up on the thread that made it, otherwise python crashes on exit
        root = shell = highway = info = big = small = big_font = small_font = title_bar = title = title_font = None
        gc.collect()

STAR = (0, -9, 2.5, -2.8, 9, -2.8, 4, 1.5, 5.8, 9, 0, 4.5, -5.8, 9, -4, 1.5, -9, -2.8, -2.5, -2.8)

def fit_text(text, font, width):
    # one line only: a name that is too long gets cut and ends in dots
    if font.measure(text) <= width:
        return text
    while text and font.measure(text + "...") > width:
        text = text[:-1]
    return text.rstrip() + "..."

def draw_highway(canvas, data):
    # runs every frame, so the canvas items are kept and moved instead of being rebuilt
    state = getattr(canvas, "highway_state", None)
    if state is None:
        state = canvas.highway_state = {"static": "", "held": None}
    width = int(canvas["width"])
    height = int(canvas["height"])
    lanes = data["lanes"] if data else []
    top = 36
    hit_line = height - 43
    left = 9

    static = tuple(lanes) if data else None
    if static != state["static"]:
        canvas.delete("all")
        state.update(static=static, held=None, ovals=[], stars=[], labels=[], used=[0, 0, 0], fills={}, texts={})
        canvas.create_rectangle(1, 1, width - 1, height - 1, fill="#131720", outline="#394252")
        if not lanes:
            canvas.create_text(width / 2, height / 2, text="WAITING FOR SONG", fill=COLORS["dim"], font=(FONT, 10, "bold"))
            return
        lane_width = (width - 18) / len(lanes)
        for lane, key in enumerate(lanes):
            x0 = left + lane * lane_width
            x1 = x0 + lane_width
            canvas.create_rectangle(x0 + 1, top, x1 - 1, hit_line + 8, fill="#1c222d", outline="#333b49")
            canvas.create_text((x0 + x1) / 2, 12, text=key.upper(), fill=LANE_COLORS[lane % len(LANE_COLORS)], font=(FONT, 9, "bold"))
        canvas.create_line(left, hit_line, width - left, hit_line, fill=COLORS["white"], width=2)
        canvas.create_text(width - 10, hit_line + 2, anchor="ne", text="PRESS", fill=COLORS["white"], font=(FONT, 7, "bold"))
    if not lanes:
        return
    lane_width = (width - 18) / len(lanes)

    held = tuple(sorted(set(data["held"])))
    if held != state["held"]:
        state["held"] = held
        canvas.delete("held")
        for lane in held:
            if lane < 0 or lane >= len(lanes):
                continue
            x0 = left + lane * lane_width
            x1 = x0 + lane_width
            canvas.create_rectangle(x0 + 3, hit_line + 12, x1 - 3, height - 5, fill=LANE_COLORS[lane % len(LANE_COLORS)], outline="", tags="held")
            canvas.create_text((x0 + x1) / 2, height - 14, text=lanes[lane].upper(), fill="#10141b", font=(FONT, 11, "bold"), tags="held")

    ovals, stars, labels = state["ovals"], state["stars"], state["labels"]
    fills, texts = state["fills"], state["texts"]
    oval_count = star_count = label_count = 0
    for lane, seconds, kind in data["notes"]:
        if lane < 0 or lane >= len(lanes):
            continue
        center = left + lane * lane_width + lane_width / 2
        y = hit_line - min(max(seconds, 0.0), 2.5) / 2.5 * (hit_line - top)
        if kind == "overdrive":
            if star_count == len(stars):
                stars.append(canvas.create_polygon(*STAR, fill=OVERDRIVE_COLOR, outline=COLORS["white"], width=1))
            points = [value + (y if index % 2 else center) for index, value in enumerate(STAR)]
            canvas.coords(stars[star_count], *points)
            star_count += 1
        else:
            if oval_count == len(ovals):
                ovals.append(canvas.create_oval(0, 0, 0, 0, outline=COLORS["white"], width=1))
            item = ovals[oval_count]
            radius = 9 if kind == "hold" else 7
            canvas.coords(item, center - radius, y - radius, center + radius, y + radius)
            color = LANE_COLORS[lane % len(LANE_COLORS)]
            if fills.get(item) != color:
                fills[item] = color
                canvas.itemconfigure(item, fill=color)
            oval_count += 1
        if label_count == len(labels):
            labels.append(canvas.create_text(0, 0, fill=COLORS["white"], font=(FONT, 7, "bold")))
        item = labels[label_count]
        canvas.coords(item, center, y - 14)
        text = f"{seconds:.1f}s"
        if texts.get(item) != text:
            texts[item] = text
            canvas.itemconfigure(item, text=text)
        label_count += 1

    # park the spare items off screen, hiding them costs more than moving them
    used = state["used"]
    for pool, count, index in ((ovals, oval_count, 0), (stars, star_count, 1), (labels, label_count, 2)):
        for item in pool[count:used[index]]:
            canvas.coords(item, *([-100] * len(canvas.coords(item))))
        used[index] = count
