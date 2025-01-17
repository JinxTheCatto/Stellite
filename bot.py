# NOTE TO ANYBODY TRYING TO SELL THIS CODE (for some reason, its so bad vro)
# The source is under a AGPL-3.0 License, although I suspect you know that.
# If you try to sell this code, release it as closed source, or don't give credit to me and Stellite, as I already have been doing, I will take it down.

import time
import keyboard
import cv2
import numpy as np
import bettercam
import ctypes
from colorama import Fore, Back, Style
import os
import json
import threading
import win32api
import win32gui
import win32con

# Set console title
os.system("title Stellite Autoplayer Console")

# Clear the console
def cls():
    os.system('cls' if os.name == 'nt' else 'clear')
cls()

# Load configuration
try:
    config = json.load(open("config.json", "r"))
except Exception as e:
    print(Back.RED + Fore.WHITE + f"ERROR: Failed to load configuration file. {str(e)}" + Back.RESET + Fore.RESET)
    exit()

monitor_width = ctypes.windll.user32.GetSystemMetrics(0)
monitor_height = ctypes.windll.user32.GetSystemMetrics(1)

if config.get("console_window_ontop") == "true":
    global hwnd
    hwnd_list = []
    def findit(hwnd, ctx):
        if win32gui.GetWindowText(hwnd).find("Stellite Autoplayer Console") != -1:
            hwnd_list.append(hwnd)
    win32gui.EnumWindows(findit, None)
    if len(hwnd_list) == 1:
        hwnd = hwnd_list[0]
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        except Exception as e:
            print(Back.RED + Fore.WHITE + f"ERROR: {str(e)} while setting window position." + Back.RESET + Fore.RESET)
    else:
        print(Back.RED + Fore.WHITE + "ERROR: Console window handle not found or multiple windows detected." + Back.RESET + Fore.RESET)

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
print("Join our discord at https://discord.gg/PcW8tSN3r4")
print("THIS PROJECT IS UNDER THE AGPL-3 LICENSE!")
if not config["always_single_lanemode"] == "true":
    number_of_lanes = int(input("Number of lanes (4 = easy-hard, 5 = expert): "))
else:
    number_of_lanes = config["single_lanemode_lanes"]

assert number_of_lanes in [4, 5], Back.RED + Fore.WHITE + "Number of lanes must be 4 or 5" + Back.RESET + Fore.RESET

print(Fore.GREEN + f"WILL ONLY AUTOPLAY WHILE CAPS LOCK IS ON! CURRENT CAPSLOCK STATUS: " + ("On" if win32api.GetKeyState(0x14) else "Off"))
print(Fore.YELLOW + f"Resolution: {monitor_width}x{monitor_height}" + Fore.RESET)
print(f"Program started, press {str.upper(config['exit_key'])} to exit")

image_found = False
for filename in os.listdir("assets"):
    if filename == str(monitor_height):
        image_found = True
        break
if not image_found:
    print(Back.RED + Fore.WHITE + "No match images in the assets folder found with the current monitor height! Please make sure you have an image made." + Back.RESET + Fore.RESET)
    exit()

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

main_camera = bettercam.create(output_color = "GRAY", max_buffer_len=512)
main_camera.start(region = (region_fromleft, region_fromtop, width, height), target_fps=config["capture_fps"])
boxed_screenshot = main_camera.get_latest_frame()

lane_cooldowns = {
    str(config["key_1"]): 0.0,
    str(config["key_2"]): 0.0,
    str(config["key_3"]): 0.0,
    str(config["key_4"]): 0.0,
    str(config["key_5"]): 0.0
}

def truncate(n, decimals = 0):
    multiplier = 10 ** decimals
    return int(n * multiplier) / multiplier

def cooldown(key):
    lane_cooldowns[key] = config["max_lane_cooldown"]
    time.sleep(config["max_lane_cooldown"])
    lane_cooldowns[key] = 0.0

def press(key, hold = False):
    print(Fore.GREEN + f"{time.time()}: Pressing {str.capitalize(key)}" + Fore.RESET)
    # if keyboard.is_pressed(key): 
    #    keyboard.release(key)
    keyboard.press(key)
    time.sleep(config["keypress_holdtime"])
    keyboard.release(key)
    threading.Thread(target=cooldown, args=(key,)).start()

def press_tile(key, hold = False):
    if lane_cooldowns[key] == 0.0:
        threading.Thread(target=press, args=(key, hold)).start()
    else:
        print(Fore.RED + f"Skipping lane {key} due to cooldown" + Fore.RESET)

tile = cv2.imread(f'assets/{monitor_height}/tile{config["tile_filename_suffix"]}.png', cv2.IMREAD_GRAYSCALE)
tile_width = tile.shape[1]
tile_height = tile.shape[0]
tile = tile.astype(np.uint8)
if config["use_white_tile"] == "true":
    white_tile = cv2.imread(f'assets/{monitor_height}/white{config["tile_filename_suffix"]}.png', cv2.IMREAD_GRAYSCALE)
    white_tile_width = white_tile.shape[1]
    white_tile_height = white_tile.shape[0]
    white_tile = white_tile.astype(np.uint8)
if config["use_battlestage_tile"] == "true":
    battlestage_tile = cv2.imread(f'assets/{monitor_height}/battlestage{config["tile_filename_suffix"]}.png', cv2.IMREAD_GRAYSCALE)
    battlestage_tile_width = battlestage_tile.shape[1]
    battlestage_tile_height = battlestage_tile.shape[0]
    battlestage_tile = battlestage_tile.astype(np.uint8)
if config["use_diamond_tile"] == "true":
    diamond_tile = cv2.imread(f'assets/{monitor_height}/diamond{config["tile_filename_suffix"]}.png', cv2.IMREAD_GRAYSCALE)
    diamond_tile_width = diamond_tile.shape[1]
    diamond_tile_height = diamond_tile.shape[0]
    diamond_tile = diamond_tile.astype(np.uint8)

def press_tiles(rectangles, results):
    for (x, y, w, h) in rectangles:
        tile_position = (x + (w // 2), y + (h // 2))
        #print(f"Found tile at {tile_position} confidence: 
        tile_lane = config[f"key_{tile_position[0] // section_size + 1}"]
        if tile_position[1] >= min_tile_pixels_top_offset:
            press_tile(tile_lane)

        if config["debug_positions"]:
            print(f"Found tile in lane {str.capitalize(tile_lane)} with confidence {truncate(results[y][x], 2)}")

def tile_logic(screenshot_np):
    results = cv2.matchTemplate(screenshot_np, tile, cv2.TM_CCOEFF_NORMED)
    locations = np.where(results >= config["min_confidence"])

    rectangles = []
    for positions in zip(*locations[::-1]):
        rectangles.append((int(positions[0]), int(positions[1]), int(tile_width), int(tile_height)))
        rectangles.append((int(positions[0]), int(positions[1]), int(tile_width), int(tile_height)))
    rectangles, weights = cv2.groupRectangles(rectangles, 1, 0.2)

    threading.Thread(target=press_tiles, args=(rectangles, results)).start()

def white_tile_logic(screenshot_np):
    results = cv2.matchTemplate(screenshot_np, white_tile, cv2.TM_CCOEFF_NORMED)
    locations = np.where(results >= config["white_tile_min_confidence"])

    rectangles = []
    for positions in zip(*locations[::-1]):
        rectangles.append((int(positions[0]), int(positions[1]), int(white_tile_width), int(white_tile_height)))
        rectangles.append((int(positions[0]), int(positions[1]), int(white_tile_width), int(white_tile_height)))
    rectangles, weights = cv2.groupRectangles(rectangles, 1, 0.2)

    threading.Thread(target=press_tiles, args=(rectangles, results)).start()

def battlestage_tile_logic(screenshot_np):
    results = cv2.matchTemplate(screenshot_np, battlestage_tile, cv2.TM_CCOEFF_NORMED)
    locations = np.where(results >= config["battlestage_tile_min_confidence"])

    rectangles = []
    for positions in zip(*locations[::-1]):
        rectangles.append((int(positions[0]), int(positions[1]), int(battlestage_tile_width), int(battlestage_tile_height)))
        rectangles.append((int(positions[0]), int(positions[1]), int(battlestage_tile_width), int(battlestage_tile_height)))
    rectangles, weights = cv2.groupRectangles(rectangles, 1, 0.2)

    threading.Thread(target=press_tiles, args=(rectangles, results)).start()

def diamond_tile_logic(screenshot_np):
    results = cv2.matchTemplate(screenshot_np, diamond_tile, cv2.TM_CCOEFF_NORMED)
    locations = np.where(results >= config["diamond_tile_min_confidence"])

    rectangles = []
    for positions in zip(*locations[::-1]):
        rectangles.append((int(positions[0]), int(positions[1]), int(diamond_tile_width), int(diamond_tile_height)))
        rectangles.append((int(positions[0]), int(positions[1]), int(diamond_tile_width), int(diamond_tile_height)))
    rectangles, weights = cv2.groupRectangles(rectangles, 1, 0.2)

    threading.Thread(target=press_tiles, args=(rectangles, results)).start()

while not keyboard.is_pressed(config['exit_key']):
    screenshot_np = main_camera.get_latest_frame()
    capslock_status = win32api.GetKeyState(0x14)
    if capslock_status and screenshot_np is not None:
        threading.Thread(target=tile_logic, args=(screenshot_np,)).start()
        if config["use_white_tile"] == "true":
            threading.Thread(target=white_tile_logic, args=(screenshot_np,)).start()
        if config["use_battlestage_tile"] == "true":
            threading.Thread(target=battlestage_tile_logic, args=(screenshot_np,)).start()
        if config["use_diamond_tile"] == "true":
            threading.Thread(target=diamond_tile_logic, args=(screenshot_np,)).start()

# STOP
main_camera.stop()
if config["console_window_ontop"] == "true":
    win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

print(Fore.WHITE + Back.RED + "Stop key pressed. Exiting Stellite..." + Fore.RESET + Back.RESET)