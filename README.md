# `Stellite, by Jinx`
`THIS PROJECT IS LICENSED UNDER AGPL-3`

![logo](https://github.com/JinxTheCatto/Stellite/assets/59938808/0933bfe3-dbf1-43c8-9c00-d4c168a66944)

Press the button below to join the discord for help, config explanations, feature requests, and bug reports

[![discord server](https://dcbadge.vercel.app/api/server/bkWf3AqrEY)](https://discord.gg/bkWf3AqrEY)

## What is Stellite?
Stellite is the world's first Fortnite Festival autoplayer, with high customizability and a useful featureset.

You can [see an early version in action here](https://www.youtube.com/watch?v=2ho50fxCqPs)

## What's new in v2
- Plays from the song's chart instead of just reacting to the screen, so every note is pressed at the exact time
- Holds sustains, so lead, bass, vocals, pro lead and pro bass are playable now, not just drums
- Activates overdrive on its own, following the optimal path from fnfpaths
- Overlay with the song timer (counting down like the one in game) and when the next overdrive is
- One timing setting that checks clear in-game hit grades while playing; `-` and `=` remain available
- Works on Windows display scaling (125%, 150%...), no more crash at 1440p, no more double presses, faster screen reading
- Resolutions without their own match images use the closest ones scaled

## How does it play?
Stellite plays straight from the song's chart. Pick the song and instrument when it starts, and Stellite downloads the chart from [fnfpaths](https://fnfpaths.github.io) and reads every note, sustain, tempo change and the optimal overdrive path out of it.

The game has no way of telling Stellite where the song is, so it still watches the highway. Until it knows where the song is it plays from the screen like it always has, and as soon as the notes it sees line up with the chart (usually a few seconds in) it switches to playing from the chart. After that, matching screen detections fine-tune the chart clock; a temporary detection gap does not interrupt chart playback. After a pause or a restart in game the chart finds its place again by itself from the game's song timer (see below); `R` tells it at once that the song was restarted.

For chart play, Stellite also checks the game's visible hit grade and combo locally. If a batch of clearly read grades contains Goods, it briefly compares the current timing with offsets 5 ms earlier and later, then keeps and saves the best measured setting. These short trials can produce a few Goods. If the first clear batch is all Perfect, it leaves the timing alone. Unclear OCR or missed combo updates are ignored, and no gameplay images are sent to an online service. You can press `-` or `=` to stop a trial and adjust timing yourself.

Playing from the chart means:
- Every note is pressed at the exact time, chords included, with no missed or doubled notes
- Sustains are held for their full length, so lead, bass, vocals and the pro parts are playable, not just drums
- Overdrive is activated on the optimal path from fnfpaths, in the middle of each activation window
- Timing is tuned with one offset instead of a pile of detection values

When a song has no saved screen-learned chart, Stellite records note timings from the highway while you play. After the song finishes, it saves the chart only if its lane and sustain counts closely match the source chart; otherwise Stellite keeps using the source chart. Drum sustain lengths come from the source chart because screen graphics caused false holds.

Screen learning uses `screen_learning_confidence` (default `0.55`) separately from the normal `min_confidence`. Lower-confidence detections help learn and sync the chart; only normal-confidence detections can trigger live screen taps before chart sync.

On Expert, when a single note repeats on the same key very quickly, the game joins the two into one tall note with an arrow on top (a lift note): press at its bottom, keep holding, let go at its top. It goes by time: pairs up to about 94 ms apart are joined (16ths at 160 bpm and faster, and anything quicker), pairs 96 ms and more apart are two ordinary notes that each need a press. Stellite works out from the chart which notes these are and plays them that way, one press and one release. Overdrive notes are joined the same way; chords and sustains are played as ordinary presses.

While a song plays, the game shows the time left under the song name. Stellite reads it once a second while the chart is not synced yet, and with the song length that says where the song is to within a second. That is how the chart finds its place when it was loaded after the song began, or in a riff that repeats: a few notes that fit at that spot are enough. Every five seconds during play the same timer checks the chart clock, and if the clock is more than three seconds away from it (the song was paused or restarted, or `]` was pressed at the wrong moment) the chart syncs again from the timer.

The terminal centers one tile per lane key plus the overdrive key (Space by default), lighting each while Stellite holds it. During chart play, Stellite watches the fixed center prompt and taps `B` once when the game displays `B GESTO`, rather than guessing emote times from chart rests. With Caps Lock on, press `]` when the first note reaches the hit line: Stellite immediately hits the chart's first note and starts the chart clock. The screen reader then fine-tunes sync as more notes appear.

When chart sync locks, either automatically or with `]` on the first note, Stellite starts a full-screen FFmpeg recording and saves it under `data/recordings` when the song ends or Stellite exits. Automatic sync may take a few seconds and miss the song intro. FFmpeg must be on PATH or installed through WinGet.

Starting Stellite clears the logs and recordings of earlier runs, except the last run that played: its log and its three newest recordings move to `data/last_run`, in place of the run kept before, so it can still be looked at after a restart.

Console events, including chart presses, skipped chart keys, and sync warnings, are saved as plain text in `data/logs` for each run. A chart press omitted because the scheduler is at least 50 ms late is reported as `Skipped chart key <key>` with its lateness. This does not detect whether Fortnite registered an on-time press. With Caps Lock off, presses of the configured lane keys, overdrive key, and `B` are logged as manual key presses.

## Limitations
- Song charts are expert only (5 lanes). On easy to hard Stellite plays from the screen only, which can't hold sustains
- Songs that aren't on fnfpaths yet only get screen reading. New songs usually show up within a few days
- Lift notes (the arrows on lead, bass and vocals) aren't marked on fnfpaths, so Stellite works them out from how close two notes on a key are. A pair it gets wrong is a missed note, so these are the notes most likely to slip
- Stellite supports most standard resolutions. Resolutions without their own match images use the closest ones scaled, which might need the confidence values tuned. You can make your own according to the naming scheme in the assets folder

## Benefits
### Performance benefits:
- Stellite can play the large majority of songs flawlessly on any difficulty, including expert.
- Stellite can achieve high rankings worldwide, even first place, depending on the presence of exploited scores for that song. Overdrive routes are important for podium positions, and Stellite now follows them on its own.
- Stellite does not trigger the anticheat and it never will unless EAC goes the valorant route.

### Account benefits:
- Gain free Season Levels for the battle pass via the Try Fortnite Festival quest line.
- Earn Festival Points and claim free rewards through various quest lines.

## Usage (tutorial video soon)
- Use Python 3.10 or newer (tested on 3.12)
- Play Fortnite on windowed fullscreen, and preferably low quality rendering mode (this makes brightness match with what the match images use)
- Use the setup.bat script to install dependencies
- Run the start.bat script, pick a song and instrument (type to search, Tab autofills, Esc skips). Answer `Y` after each song to queue another; Stellite loads the next chart when the current chart ends. When the queue is empty, it asks whether you want to pick another song. Start each next song in Fortnite as usual
- Turn caps lock on before the song starts, Stellite only plays while caps lock is on
- If clear Goods are detected, Stellite briefly checks nearby timing offsets; use `-` or `=` for manual adjustment (see [Timing](#timing))
- Restart the program after altering the config file, if needed
- Join the discord for the config values explanation

### Upgrading from v1
Replace the old files with the new ones, keep your config.json, and run setup.bat again. Old configs still work, anything missing uses its default. If your old config has `debug_positions` set to `"true"`, set it to `"false"` unless you need it, v1 printed debug lines no matter what that setting was.

### Hotkeys
These all work while Fortnite is open.

| Key | What it does |
| --- | --- |
| Caps Lock | Autoplay on/off. While it is off the overlay can be dragged around |
| `[` | **Pick a different current song.** Press it, click the Stellite window, type the song name and pick the instrument. Autoplay pauses until you are done; any songs already queued stay queued |
| `]` | **Optional: hit the first note and sync by hand.** Stellite starts by itself: it plays the first notes from the screen and switches to the chart after about four of them. If you prefer, keep Caps Lock on and press `]` once when the first note reaches the hit line. Stellite presses that note and syncs the chart; the screen reader fine-tunes timing afterward. Once the song is under way the key does nothing, the chart finds its place from the game's song timer |
| `R` | **Song restarted.** Press it when you restart the song in game. Stellite drops its chart clock and syncs again from the start (`restart_key`) |
| `\` | **Read the song from the screen now.** On the ready screen it reads the song cards and your part; while a song is playing it reads the song name at the bottom left. For when the song was not picked up by itself (`read_screen_key`) |
| `-` | **Play earlier.** Moves every note 5 ms earlier and saves it. Press it while playing if you get Goods instead of Perfects |
| `=` | **Play later.** Moves every note 5 ms later and saves it, for when you went too far |
| `Ctrl+Q` | Exit |

### Ready screen
While no song is playing, Stellite checks the screen once a second for the ready screen. It reads the up to 4 songs in the setlist and your part, loads the first one and queues the rest, so you do not have to type anything. It needs Expert difficulty and a normal part (Pro Lead and Pro Bass are not supported), and reads Spanish and English menus. `[` still works if it reads the wrong song.

### Overlay
The overlay opens on the left and never takes focus from Fortnite. Its mini highway shows the next 2.5 seconds of scheduled chart notes moving toward the `PRESS` line; Overdrive phrase notes are white stars, and a lane lights while its key is held. The timer and status are beside it. Turn Caps Lock off to drag the overlay; it remembers its position.
- The big number is the song timer, counting down like the one in game
- The bar across the top names the song and part that are loaded, so you can see what it picked up
- `OD 2:31  3rd RY` means overdrive gets activated when the timer hits 2:31, on the 3rd RY chord, and `OD NOW` shows when it happens
- `SYNCING` means the screen reader is lining the chart up; `CAPS OFF` means autoplay is paused
- After `-` or `=` it shows the new timing for a moment, like `notes 15 ms earlier`

## Timing
When Stellite plays from the chart every note uses the same timing, so if one note is a little late they all are. Stellite checks clear on-screen grades and may compare short batches at the current offset and ±5 ms. If you prefer to tune manually:
1. Play a song and watch the hit feedback
2. If you get Goods, press `-` a few times while playing until they turn into Perfects. If you go too far and get Goods again, press `=`
3. That's it, Stellite saves it to config.json by itself and tells you in plain words, like `Notes now play 15 ms earlier`

| Setting | What it does | Default |
| --- | --- | --- |
| `chart_timing_offset_ms` | **The main one.** When notes get pressed. Minus is earlier, plus is later, so `-15` means 15 ms earlier. `-` and `=` change it for you | `0` |
| `overdrive_timing_offset_ms` | Extra shift for overdrive only, on top of the note timing. Overdrive has a lot of room, so leave it at 0 | `0` |
| `chart_nudge_step_ms` | How far one press of `-` or `=` moves the timing | `5` |
| `chart_sync_tolerance_ms` | Not a timing offset. How far a note seen on screen can be from the chart and still count as in sync. Only touch it if Stellite never syncs | `50` |

Changing Fortnite's own audio or video offset can move when Stellite needs to press too, since Stellite lines up with what it sees on screen. Set those how you like first, then tune Stellite with `-` and `=`.

These are only used while Stellite plays from the screen (before it syncs, on easy to hard, or with `use_song_charts` off): `min_tile_pixels_top_offset_scaled` (how far down a note has to be before it gets pressed, lower presses earlier), `max_lane_cooldown` (wait before a lane can be pressed again). `keypress_holdtime` is how long each normal note is held in both modes.

## Config
- `use_song_charts`: play from song charts, turn off for screen reading only
- `instrument`: the instrument picked by default (drums, lead, bass, vocals). Pro Lead and Pro Bass are not offered
- `use_overdrive`, `overdrive_key`: overdrive activation, Space is the default keybind in game
- `show_overlay`: the song timer and overdrive overlay
- `auto_detect_song`: read the setlist and your part from the ready screen ("¡PREPÁRATE!" / "GET READY!") instead of typing the song in
- `min_confidence` and the tile-specific confidence values: screen-matching threshold. Higher values reduce false detections but can miss real tiles
- `song_select_key`, `sync_key`, `nudge_earlier_key`, `nudge_later_key`: hotkeys
- The timing values are explained in [Timing](#timing), the rest are the same as v1

## IMPORTANT NOTES
Currently the only built in match images are for 1440p, 1080p, and 768p, other resolutions use the closest ones scaled up or down. If notes aren't being picked up you can make your own images matching those in the assets folder with those that suite your game.

Fortnite reworked how lift notes look in August 2025. If notes aren't being picked up, try turning off Lift Notes Connectors and the Good hit feedback in Settings > Game > Festival. The Battle Stage was taken offline in April 2026, so `use_battlestage_tile` is off by default now.

When playing from the chart, the timing is usually the only thing that needs tuning, see [Timing](#timing). Screen reading (before syncing, or on easy to hard) may still need the other configuration values fine-tuned based on your resolution, processing speed, and refresh rate, especially if your resolution is something other than 1080p. Use the debug window for assistance.

![image (1)](https://github.com/JinxTheCatto/Stellite/assets/59938808/48f38ccf-3072-41d3-b832-703070346735)

## Credits
- Stellite by jinxthecat_
- Song charts and overdrive paths: [fnfpaths](https://fnfpaths.github.io), drawn with [CHOpt](https://github.com/GenericMadScientist/CHOpt)
- Song lengths for the timer: Epic's public Festival track list
- Chart reading and the overlay are based on [Festival OD Coach](https://github.com/Aknownthreat/-fortnite-festival-overdrive-timer) by Aknownthreat, made for Stellite. Copyright (C) 2026 Aknownthreat, licensed under GPL-3.0 which can be combined with AGPL-3.0

Not affiliated with Epic Games.

## THIS PROJECT IS FOR EDUCATIONAL PURPOSES ONLY

[![forthebadge](https://forthebadge.com/images/badges/0-percent-optimized.svg)]([https://forthebadge.com](https://discord.gg/bkWf3AqrEY)) [![forthebadge](https://forthebadge.com/images/badges/ctrl-c-ctrl-v.svg)](https://discord.gg/bkWf3AqrEY) [![forthebadge](https://forthebadge.com/images/badges/works-on-my-machine.svg)]([https://forthebadge.com](https://discord.gg/bkWf3AqrEY))

![tenor](https://github.com/JinxTheCatto/Stellite/assets/59938808/f8d9a998-575e-4e94-baa3-dad5102d9f5e)
