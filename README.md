# Gesture Control Toolkit

Control presentations, media, browsers, and the mouse with webcam hand gestures.
The app uses **MediaPipe Gesture Recognizer**, **OpenCV**, and **PyAutoGUI** to
send normal key presses and mouse actions to the active application.

## Features

- Profiles for `slides`, `media`, `browse`, `youtube`, `meeting`, and `mouse`
- Swipe and pose gestures, with configurable key, hotkey, scroll, and click actions
- A visible target-window label; an empty `target_window` displays **active window**
- Compact 320x240 preview with `--small`
- Action and pause/resume beeps, controlled by `sounds_enabled` in `config.json`
- Mouse control with index-finger pointing, smoothing, and pinch-to-left-click
- Tkinter profile/action editor (`--settings`)
- CSV session logs, randomized recognition evaluation (`--eval`), and a log chart
- `--dry-run` detection without sending actions

**Which app receives the gestures?** Before each action, the app brings the
window whose title contains the profile's `target_window` to the front (on
Windows). The defaults are `PowerPoint`, `Chrome`, `YouTube` and `Meet`. An empty
value sends input to whatever window is active, so on macOS/Linux click the app
once after starting.

## Setup and run

Use Python 3.10–3.12; MediaPipe may not support newer Python versions.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

The first run downloads the MediaPipe model (about 8 MB) to `models/`.
Press `q` or `Esc` in the camera preview to quit.

```powershell
python main.py --profile youtube  # choose a profile at startup
python main.py --profile meeting
python main.py --profile mouse
python main.py --small            # 320x240 camera window
python main.py --dry-run          # detect and log without sending actions
python main.py --settings         # edit mappings and save config.json
python main.py --eval             # evaluate all supported gestures
python analyze_logs.py            # summarize action logs and save a chart
python -m unittest discover tests
```

**Without VS Code (Windows):** double-click `Gesture Control.bat`. The first
time it creates `.venv` and installs everything; after that it just starts the
app. `Gesture Control (no console).vbs` starts it without the black console
window. Right-click either file → *Send to* → *Desktop (create shortcut)* to put
it on your desktop.

On Windows, if the virtual environment is not activated, invoke
`.venv\Scripts\python.exe` instead of `python`.

## Profiles

| Profile | Gestures |
|---|---|
| `slides` | Swipe left / thumbs-up: next slide; swipe right / thumbs-down: previous; fist: black screen |
| `media` | Open palm: play/pause; thumbs-up/down: volume; swipes: next/previous track |
| `browse` | Thumbs-up/down: scroll; swipes: browser forward/back |
| `youtube` | Open palm: `k` play/pause; swipes: `l` / `j` seek 10 seconds; thumbs-up/down: system volume; fist: `f` fullscreen |
| `meeting` | Fist: Ctrl+D mute toggle; open palm: Ctrl+E camera toggle |
| `mouse` | Stretched-out index finger moves the cursor; fold it (fist) to stop; pinch thumb + index = left click; pinch thumb + middle = right click. ILoveYou pauses/resumes control. |

`slides` is the default profile. Victory cycles through profiles, and ILoveYou
pauses or resumes gesture actions. The YouTube and meeting profiles use their
application keyboard shortcuts, so focus the matching app before gesturing.
Media keys work best on Windows.

The preview displays the current profile's `target_window` value, or
**active window** when it is empty. Change them in `config.json` to match your
apps (for example `"Edge"` instead of `"Chrome"`).

## Settings window

Run `python main.py --settings`, choose a profile, and select an action for each
gesture from the dropdowns. The mouse profile also has a pinch-click action
selector. **Save to config.json** writes the profile changes and sets the
selected profile as the startup profile. The dropdown includes common key,
hotkey, scroll, and click actions; existing custom actions can be left unchanged.

Set `"sounds_enabled": false` in `config.json` to mute feedback. On Windows,
actions use a short beep and pause/resume use distinct tones.

## Evaluation and logs

Run `python main.py --eval` to perform 20 randomized trials for each of the
seven MediaPipe poses and two swipe directions. Follow the on-screen prompt.
A 3-second countdown runs first. A pose only counts once it has been held for
`static.hold_frames` frames, so the shapes your hand passes through while
forming a gesture aren't recorded as errors. Trials time out after 10 seconds. The CSV in `logs/` contains each detected
gesture and reaction time, followed by accuracy and average reaction-time
summaries per gesture. Reaction-time averages use correctly detected trials.

Normal runs write session CSVs to `logs/`. Run `python analyze_logs.py` to print
action totals per gesture and profile; it saves
`logs/actions_by_gesture.png`. Evaluation CSVs are excluded from action counts.
Use `--dry-run` to observe false triggers without sending input.

## Gesture tuning

The pose hold, confidence threshold, stillness, repeat interval, and swipe
thresholds are configurable in `config.json`. A pose must be held for about
0.25 seconds by default; repeated actions such as volume changes use the
configured repeat interval.

### Mouse mode design
| Problem | Design choice | Setting (`mouse.*`) |
|---|---|---|
| Shaky cursor / laggy cursor | Adaptive smoothing: heavy for small moves, light for fast moves | `smoothing_min`, `smoothing_max`, `speed_for_max` |
| Hand tremor | Ignore tiny movements | `deadzone` |
| Cursor stops when the classifier flickers | Move whenever the index finger is stretched out (finger geometry), not only on the `Pointing_Up` label | – |
| Pinch only works at one distance | Pinch measured relative to hand size | `pinch_on` |
| One pinch = several clicks | Two thresholds (hysteresis) + cooldown | `pinch_off`, `click_cooldown_seconds` |
| Cursor drifts while you form a fist or pinch | Follow the index **knuckle**, not the fingertip, and **rewind** the cursor to where it was 0.2 s before the click/stop | `pointer`, `rewind_seconds` |
| Cursor moves during a click | Cursor freezes while pinching | – |
| No right click | Pinch thumb + middle finger | `right_pinch_action` |
| Screen edges unreachable | Only the middle of the camera image maps to the whole screen | `edge_margin` |
| App stops at screen corners | Cursor stays 1 px from the edges (PyAutoGUI fail-safe) | – |

## Code and limitations

- `logic.py` contains camera-independent gesture and mouse-control logic.
- `detector.py` wraps MediaPipe.
- `actions.py` sends key, scroll, mouse, and sound feedback.
- `evaluation.py`, `settings.py`, and `analyze_logs.py` implement evaluation,
  configuration, and log analysis.
- Lighting and camera quality affect recognition. Only one hand and MediaPipe's
  built-in gestures are supported.

## Privacy

All processing happens on your computer. Camera frames are analysed and then
discarded: no video or images are saved or sent anywhere. Logs only contain
times, profile names, gesture names and actions.

## License

MIT
