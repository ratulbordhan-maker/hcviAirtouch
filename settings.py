"""Tkinter editor for profile gesture-to-action mappings."""

import copy
import json
import os
import tkinter as tk
from tkinter import messagebox, ttk

GESTURES = (
    "swipe_left",
    "swipe_right",
    "Closed_Fist",
    "Open_Palm",
    "Pointing_Up",
    "Thumb_Down",
    "Thumb_Up",
    "Victory",
    "ILoveYou",
)
PINCH_KEYS = {"Pinch": "pinch_action", "Right pinch": "right_pinch_action"}
SPECIAL_DEFAULTS = {
    "Victory": "Switch profile",
    "ILoveYou": "Pause / resume",
}

ACTION_PRESETS = {
    "Switch profile": {"type": "control", "action": "profile"},
    "Pause / resume": {"type": "control", "action": "toggle"},
    "Next slide (Right arrow)": {
        "type": "key", "key": "right", "label": "Next slide",
    },
    "Previous slide (Left arrow)": {
        "type": "key", "key": "left", "label": "Previous slide",
    },
    "Black screen (B)": {
        "type": "key", "key": "b", "label": "Black screen",
    },
    "Play / pause (K)": {
        "type": "key", "key": "k", "label": "Play / pause",
    },
    "Volume up": {
        "type": "key", "key": "volumeup", "label": "Volume up", "repeat": True,
    },
    "Volume down": {
        "type": "key", "key": "volumedown", "label": "Volume down", "repeat": True,
    },
    "Forward 10 seconds (L)": {
        "type": "key", "key": "l", "label": "Forward 10 seconds",
    },
    "Back 10 seconds (J)": {
        "type": "key", "key": "j", "label": "Back 10 seconds",
    },
    "Fullscreen (F)": {
        "type": "key", "key": "f", "label": "Fullscreen",
    },
    "Toggle mute (Ctrl+D)": {
        "type": "hotkey", "keys": ["ctrl", "d"], "label": "Toggle mute",
    },
    "Toggle camera (Ctrl+E)": {
        "type": "hotkey", "keys": ["ctrl", "e"], "label": "Toggle camera",
    },
    "Scroll up": {
        "type": "scroll", "amount": 300, "label": "Scroll up", "repeat": True,
    },
    "Scroll down": {
        "type": "scroll", "amount": -300, "label": "Scroll down", "repeat": True,
    },
    "Left click": {
        "type": "mouse_click", "button": "left", "label": "Left click",
    },
    "Right click": {
        "type": "mouse_click", "button": "right", "label": "Right click",
    },
}


def _signature(action):
    if not action:
        return None
    kind = action.get("type")
    if kind == "key":
        return kind, action.get("key")
    if kind == "hotkey":
        return kind, tuple(action.get("keys", ()))
    if kind == "scroll":
        return kind, action.get("amount")
    if kind == "mouse_click":
        return kind, action.get("button", "left")
    if kind == "control":
        return kind, action.get("action")
    return kind, json.dumps(action, sort_keys=True)


def open_settings(config_path="config.json"):
    with open(config_path, encoding="utf-8") as file:
        config = json.load(file)

    profile_names = list(config["profiles"])
    root = tk.Tk()
    root.title("Gesture Control Settings")
    root.minsize(480, 420)
    root.columnconfigure(0, weight=1)

    profile_var = tk.StringVar(
        value=config.get("active_profile", profile_names[0])
    )
    if profile_var.get() not in profile_names:
        profile_var.set(profile_names[0])
    ttk.Label(root, text="Profile").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
    profile_picker = ttk.Combobox(
        root, textvariable=profile_var, values=profile_names, state="readonly"
    )
    profile_picker.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))

    rows_frame = ttk.Frame(root)
    rows_frame.grid(row=2, column=0, sticky="nsew", padx=12)
    root.rowconfigure(2, weight=1)
    variables = {}
    custom_actions = {}
    displayed_profile = profile_var.get()

    def apply_displayed_profile():
        profile = config["profiles"][displayed_profile]
        for key, var in variables.items():
            action_key = PINCH_KEYS.get(key, key)
            choice = var.get()
            if choice == "No action":
                if key in SPECIAL_DEFAULTS:
                    profile[action_key] = {"type": "control", "action": "disabled"}
                else:
                    profile.pop(action_key, None)
            elif choice == "Keep current custom action":
                profile[action_key] = copy.deepcopy(custom_actions[key])
            else:
                profile[action_key] = copy.deepcopy(ACTION_PRESETS[choice])

    def build_rows():
        nonlocal displayed_profile
        displayed_profile = profile_var.get()
        for child in rows_frame.winfo_children():
            child.destroy()
        variables.clear()
        custom_actions.clear()

        profile = config["profiles"][displayed_profile]
        gestures = list(GESTURES)
        if profile.get("mode") == "mouse":
            gestures.extend(PINCH_KEYS)
        for row, gesture in enumerate(gestures):
            action_key = PINCH_KEYS.get(gesture, gesture)
            current = profile.get(action_key)
            presets = {
                name: action
                for name, action in ACTION_PRESETS.items()
                if gesture in SPECIAL_DEFAULTS or action.get("type") != "control"
            }
            options = ["No action", *presets]
            if current is None:
                selected = SPECIAL_DEFAULTS.get(gesture, "No action")
            elif (gesture in SPECIAL_DEFAULTS
                  and current == {"type": "control", "action": "disabled"}):
                selected = "No action"
            else:
                signature = _signature(current)
                selected = next(
                    (name for name, action in presets.items()
                     if _signature(action) == signature),
                    None,
                )
                if selected is None:
                    selected = "Keep current custom action"
                    options.append(selected)
                    custom_actions[gesture] = copy.deepcopy(current)

            ttk.Label(rows_frame, text=gesture).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=3
            )
            var = tk.StringVar(value=selected)
            picker = ttk.Combobox(
                rows_frame, textvariable=var, values=options, state="readonly",
                width=30,
            )
            picker.grid(row=row, column=1, sticky="ew", pady=3)
            variables[gesture] = var
        rows_frame.columnconfigure(1, weight=1)

    def change_profile(_event=None):
        nonlocal displayed_profile
        apply_displayed_profile()
        displayed_profile = profile_var.get()
        build_rows()

    def save():
        apply_displayed_profile()
        config["active_profile"] = profile_var.get()
        temp_path = f"{config_path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as file:
                json.dump(config, file, indent=2)
                file.write("\n")
            os.replace(temp_path, config_path)
        except OSError as error:
            messagebox.showerror("Could not save settings", str(error), parent=root)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return
        messagebox.showinfo("Settings saved", f"Saved changes to {config_path}", parent=root)

    profile_picker.bind("<<ComboboxSelected>>", change_profile)
    build_rows()
    ttk.Button(root, text="Save to config.json", command=save).grid(
        row=3, column=0, sticky="e", padx=12, pady=12
    )
    root.mainloop()
