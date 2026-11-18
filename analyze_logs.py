"""Summarize logged gesture actions and save a grouped bar chart."""

import csv
import glob
import os
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def read_action_counts(folder="logs"):
    by_gesture = Counter()
    by_profile = Counter()
    by_pair = Counter()

    for path in sorted(glob.glob(os.path.join(folder, "*.csv"))):
        with open(path, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            if not {"profile", "event_type", "trigger"}.issubset(reader.fieldnames or ()):
                continue
            for row in reader:
                if row.get("event_type") != "action":
                    continue
                gesture = (row.get("trigger") or "").strip()
                profile = (row.get("profile") or "").strip()
                if not gesture or not profile:
                    continue
                by_gesture[gesture] += 1
                by_profile[profile] += 1
                by_pair[(gesture, profile)] += 1
    return by_gesture, by_profile, by_pair


def save_chart(by_gesture, by_profile, by_pair, path):
    gestures = sorted(by_gesture)
    profiles = sorted(by_profile)
    figure, axis = plt.subplots(figsize=(max(8, len(gestures) * 1.1), 5))

    if gestures and profiles:
        group_width = 0.8
        bar_width = group_width / len(profiles)
        centers = list(range(len(gestures)))
        for profile_index, profile in enumerate(profiles):
            offsets = [
                center - group_width / 2 + bar_width * (profile_index + 0.5)
                for center in centers
            ]
            values = [by_pair[(gesture, profile)] for gesture in gestures]
            axis.bar(offsets, values, bar_width, label=profile)
        axis.set_xticks(centers)
        axis.set_xticklabels(gestures, rotation=35, ha="right")
        axis.legend(title="Profile")
        axis.set_ylabel("Actions fired")
        axis.set_title("Actions by gesture and profile")
    else:
        axis.text(0.5, 0.5, "No actions recorded", ha="center", va="center")
        axis.set_axis_off()

    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def main():
    folder = "logs"
    if not os.path.isdir(folder):
        raise SystemExit(f"Log folder not found: {folder}")

    by_gesture, by_profile, by_pair = read_action_counts(folder)
    print("Actions per profile:")
    for profile in sorted(by_profile):
        print(f"  {profile}: {by_profile[profile]}")
    print("Actions per gesture:")
    for gesture in sorted(by_gesture):
        print(f"  {gesture}: {by_gesture[gesture]}")

    chart_path = os.path.join(folder, "actions_by_gesture.png")
    save_chart(by_gesture, by_profile, by_pair, chart_path)
    print(f"Chart saved to {chart_path}")


if __name__ == "__main__":
    main()
