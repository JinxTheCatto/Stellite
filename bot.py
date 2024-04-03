# TODO:
# hold notes
# gui

try:
    import pyautogui
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
    #import win32gui
    #import customtkinter as ctk
except Exception as e:
    print(f"Error importing modules! This probably means the setup.bat script failed. Try running it again or  the server if it returns an error.")

# Gui code latr

config = json.load(open("config.json", "r"))
def cls():
    os.system('cls' if os.name == 'nt' else 'clear')
cls()
os.system("title Stellite Autoplayer")
monitor_width = ctypes.windll.user32.GetSystemMetrics(0)
monitor_height = ctypes.windll.user32.GetSystemMetrics(1)

# START
print(f'''
{Fore.RED + Style.NORMAL}      :::::::: {Fore.YELLOW}::::::::::: {Fore.YELLOW + Style.BRIGHT}:::::::::: {Fore.GREEN + Style.NORMAL}:::        {Fore.CYAN}:::        {Fore.BLUE}::::::::::: {Fore.MAGENTA}::::::::::: {Fore.MAGENTA + Style.BRIGHT}:::::::::: 
{Fore.RED + Style.NORMAL}    :+:    :+:    {Fore.YELLOW}:+:     {Fore.YELLOW + Style.BRIGHT}:+:        {Fore.GREEN + Style.NORMAL}:+:        {Fore.CYAN}:+:            {Fore.BLUE}:+:         {Fore.MAGENTA}:+:     {Fore.MAGENTA + Style.BRIGHT}:+:         
{Fore.RED + Style.NORMAL}   +:+           {Fore.YELLOW}+:+     {Fore.YELLOW + Style.BRIGHT}+:+        {Fore.GREEN + Style.NORMAL}+:+        {Fore.CYAN}+:+            {Fore.BLUE}+:+         {Fore.MAGENTA}+:+     {Fore.MAGENTA + Style.BRIGHT}+:+          
{Fore.RED + Style.NORMAL}  +#++:++#++    {Fore.YELLOW}+#+     {Fore.YELLOW + Style.BRIGHT}+#++:++#   {Fore.GREEN + Style.NORMAL}+#+        {Fore.CYAN}+#+            {Fore.BLUE}+#+         {Fore.MAGENTA}+#+     {Fore.MAGENTA + Style.BRIGHT}+#++:++#      
{Fore.RED + Style.NORMAL}        +#+    {Fore.YELLOW}+#+     {Fore.YELLOW + Style.BRIGHT}+#+        {Fore.GREEN + Style.NORMAL}+#+        {Fore.CYAN}+#+            {Fore.BLUE}+#+         {Fore.MAGENTA}+#+     {Fore.MAGENTA + Style.BRIGHT}+#+            
{Fore.RED + Style.NORMAL}#+#    #+#    {Fore.YELLOW}#+#     {Fore.YELLOW + Style.BRIGHT}#+#        {Fore.GREEN + Style.NORMAL}#+#        {Fore.CYAN}#+#            {Fore.BLUE}#+#         {Fore.MAGENTA}#+#     {Fore.MAGENTA + Style.BRIGHT}#+#             
{Fore.RED + Style.NORMAL}########     {Fore.YELLOW}###     {Fore.YELLOW + Style.BRIGHT}########## {Fore.GREEN + Style.NORMAL}########## {Fore.CYAN}########## {Fore.BLUE}###########     {Fore.MAGENTA}###     {Fore.MAGENTA + Style.BRIGHT}##########                      
''')
print(Style.RESET_ALL + Fore.RED + "The first Fortnite Festival autoplayer")
print("Project by jinxthecat_")
print("Join our discord at https://discord.gg/PcW8tSN3r4")
print("IF YOU PAID FOR THIS YOU GOT SCAMMED!")
if not config["always_single_lanemode"] == "true":
    number_of_lanes = int(input("Number of lanes (4 = easy-hard, 5 = expert): "))
else:
    number_of_lanes = config["single_lanemode_lanes"]
assert number_of_lanes in [4, 5], Back.RED + Fore.WHITE + "Number of lanes must be 4 or 5" + Back.RESET + Fore.RESET
print(Fore.GREEN + f"WILL ONLY AUTOPLAY WHILE CAPS LOCK IS ON! CURRENT CAPSLOCK STATUS: " + ("On" if win32api.GetKeyState(0x14) else "Off"))
print(Fore.YELLOW + f"Capture region color mode: {config['color_mode']}" + Fore.RESET)
print(Fore.YELLOW + f"Viewbox color mode: {config['color_mode']}")
print(f"Resolution: {monitor_width}x{monitor_height}" + Fore.RESET)
print(f"Program started, press {str.upper(config['exit_key'])} to exit")

imagefound = False
for filename in os.listdir("assets"):
    if filename.startswith(f"tile{monitor_height}"):
        imagefound = True
        break
if not imagefound:
    print(Back.RED + Fore.WHITE + "No match image in the assets folder found with the current monitor height! Please make sure you have an image made, or contact me in the discord to help me add support!" + Back.RESET + Fore.RESET)
    exit()

tile_filenames = [
        f'assets/tile{monitor_height}{config["tile_filename_suffix"]}.png',
]
#if config["detect_hold_tiles"] == "true":
    #tile_filenames.append(f'assets/tile{monitor_height}hold{config["tile_filename_suffix"]}.png')
if config["color_mode"] != "gray":
    tile_filenames.append(f'assets/tile{monitor_height}orange{config["tile_filename_suffix"]}.png')
if config["detect_diamond_tiles"] == "true":
    tile_filenames.append(f'assets/tile{monitor_height}diamond{config["tile_filename_suffix"]}.png')
tile_images = [cv2.imread(tile_filename, (cv2.IMREAD_GRAYSCALE if config["color_mode"] == "gray" else cv2.IMREAD_UNCHANGED)) for tile_filename in tile_filenames]

# 1080p values:
region_width = 555 if number_of_lanes == 4 else 696
region_height = 180 # height i actually want in the region
height_offset = 170 # higher number is looking higher
# scale values
scale_factor = 1080 / monitor_height
min_tile_pixels_top_offset = int(config["min_tile_pixels_top_offset"] // scale_factor)
if scale_factor != 1:
    region_width = int(region_width // scale_factor)
    region_height = int(region_height // scale_factor)
    height_offset = int(height_offset // scale_factor)

region_fromleft = int(((monitor_width - region_width) // 2) + (8 // scale_factor) if number_of_lanes == 5 else ((monitor_width - region_width) // 2) + 1) # higher offset is looking more right. idk why this is needed since it should be centered
region_fromtop = (monitor_height - region_height) - height_offset
width = region_fromleft + region_width
height = region_fromtop + region_height
section_size = region_width // number_of_lanes

if config["show_debug_visuals"] == "true":
    display_visuals = True
else:
    display_visuals = False

#if config["viewbox_bgra_color_override"] == "true":
    #viewboxcamera = bettercam.create(output_color="BGRA", max_buffer_len=512)
    #viewboxcamera.start(region=(region_fromleft, region_fromtop, width, height), target_fps=60)

maincamera = bettercam.create(output_color=("GRAY" if config["color_mode"] == "gray" else "BGRA"), max_buffer_len=512)
maincamera.start(region=(region_fromleft, region_fromtop, width, height), target_fps=config["capture_fps"])
cv2.namedWindow('Stellite Autoplayer View')
cv2.resizeWindow('Stellite Autoplayer View', region_width, region_height)
cv2.moveWindow('Stellite Autoplayer View', (monitor_width - region_width) - 10, 0)
cv2.setWindowProperty('Stellite Autoplayer View', cv2.WINDOW_FREERATIO, 0)
cv2.setWindowProperty('Stellite Autoplayer View', cv2.WND_PROP_TOPMOST, 1)

lane_cooldowns = {
    str(config["key_1"]): 0.0,
    str(config["key_2"]): 0.0,
    str(config["key_3"]): 0.0,
    str(config["key_4"]): 0.0,
    str(config["key_5"]): 0.0
}

def cooldown(key):
    lane_cooldowns[key] = config["max_lane_cooldown"]
    time.sleep(config["max_lane_cooldown"])
    lane_cooldowns[key] = 0.0

def press(key, hold=False):
    print(f"{time.time()}: Pressing {key}")
    #if keyboard.is_pressed(key): keyboard.release(key)
    keyboard.press(key)
    time.sleep(config["keypress_holdtime"])
    keyboard.release(key)
    threading.Thread(target=cooldown, args=(key,)).start()

def press_tile(key, hold=False):
    if lane_cooldowns[key] == 0.0:
        threading.Thread(target=press, args=(key,hold)).start()

while not keyboard.is_pressed(config['exit_key']):
    screenshot_np = maincamera.get_latest_frame()
    capslock_status = win32api.GetKeyState(0x14)
    if capslock_status and screenshot_np is not None:
        for tile_image in tile_images:
            tile_image = tile_image.astype(screenshot_np.dtype)
            tilewidth = tile_image.shape[1]
            tileheight = tile_image.shape[0]

            result = cv2.matchTemplate(screenshot_np, tile_image, cv2.TM_CCOEFF_NORMED)
            minimumdetectconfidence = ((config["diamond_tiles_min_confidence"] if tile_image.shape == tile_images[len(tile_images) - 1].shape else config["min_confidence"]) if config["detect_diamond_tiles"] == "true" else config["min_confidence"])
            locations = np.where(result >= minimumdetectconfidence)

            rectangles = []
            for positions in zip(*locations[::-1]):
                rectangles.append((int(positions[0]), int(positions[1]), int(tilewidth), int(tileheight)))
                rectangles.append((int(positions[0]), int(positions[1]), int(tilewidth), int(tileheight)))
            rectangles, weights = cv2.groupRectangles(rectangles, 1, 0.2)

            for (x, y, w, h) in rectangles:
                tile_position = (x + (tilewidth // 2), y + (tileheight // 2))
                print(f"Detected tile at position {tile_position} with confidence {result[positions[1], positions[0]]}")

                if tile_position[1] >= min_tile_pixels_top_offset:
                    if tile_position[0] <= section_size:
                        press_tile(config["key_1"])
                    elif tile_position[0] <= section_size * 2:
                        press_tile(config["key_2"])
                    elif tile_position[0] <= section_size * 3:
                        press_tile(config["key_3"])
                    elif tile_position[0] <= section_size * 4:
                        press_tile(config["key_4"])
                    elif tile_position[0] <= section_size * 5:
                        press_tile(config["key_5"])

                if display_visuals:
                    if config["color_mode"] == "gray" and config["viewbox_bgra_color_override"] == "false":
                        cv2.rectangle(screenshot_np, (x, y), (x + w, y + h), (255, 255, 255), 2)
                    else:
                        cv2.rectangle(screenshot_np, (x, y), (x + w, y + h), (0, 0, 255), 2)

    if display_visuals:
        capslock_text = "CAPS LOCK: ON" if capslock_status else "CAPS LOCK: OFF"

        if config["color_mode"] == "gray" and config["viewbox_bgra_color_override"] == "false":
            cv2.putText(screenshot_np, capslock_text, (0, 15), cv2.FONT_HERSHEY_PLAIN, 1, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow('Stellite Autoplayer View', screenshot_np)
        else:
            cv2.putText(screenshot_np, capslock_text, (0, 15), cv2.FONT_HERSHEY_PLAIN, 1, ((0, 255, 0) if capslock_status else (0, 0, 255)), 1, cv2.LINE_AA)
            cv2.imshow('Stellite Autoplayer View', viewboxcamera.grab())
        cv2.waitKey(1)

# STOP
cv2.destroyAllWindows()
maincamera.stop()

#cls()
print(Fore.WHITE + Back.RED + "Stop key pressed. Exiting Stellite..." + Fore.RESET + Back.RESET)