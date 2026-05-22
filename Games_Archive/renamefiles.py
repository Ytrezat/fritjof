#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Mar 25 10:26:24 2026

@author: thibault
"""

import json
import re
from pathlib import Path
from datetime import datetime

# ====== CONFIG ======
FOLDER = Path(".")               # folder with your .txt files
GAMES_JSON = FOLDER / "games.json"
DRY_RUN = False                  # True = preview only, False = actually rename/write
# ====================

def normalize_display_name(name: str) -> str:
    """
    For JSON display names only.
    Example: Black_Raven -> Black Raven
    """
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.replace("_", " ")
    name = re.sub(r'\s+', ' ', name)
    return name

def sanitize_filename_part(name: str) -> str:
    """
    Safe for filenames. Removes forbidden chars and removes spaces/underscores.
    """
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.replace("_", "")
    name = re.sub(r'\s+', '', name)   # remove spaces
    return name


def extract_player(line: str, label: str) -> str | None:
    """
    Extract player name from lines like:
    White:  Casshern, Los Angeles, USA
    Black:  Draganov, Sofia, Bulgaria
    Takes the first comma-separated field after the label.
    """
    m = re.match(rf'^{label}:\s*(.+)$', line.strip(), re.IGNORECASE)
    if not m:
        return None
    content = m.group(1).strip()
    player = content.split(",")[0].strip()
    return sanitize_filename_part(player)


def extract_event_line(lines: list[str]) -> str | None:
    for line in lines:
        if line.strip().lower().startswith("event:"):
            return line.strip()
    return None


def extract_event_text(event_line: str | None) -> str:
    """
    'Event: WTF World Championship Tournament 2025'
    -> 'WTF World Championship Tournament 2025'
    """
    if not event_line:
        return ""
    m = re.match(r'^Event:\s*(.+)$', event_line, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def extract_event_code(event_text: str) -> str:
    """
    Filename event code:
    'WTF World Championship Tournament 2025' -> 'WTF'
    (date already exists elsewhere, so no need to append year)
    """
    # Prefer an ALL-CAPS abbreviation like WTF
    code_match = re.search(r'\b([A-Z]{2,})\b', event_text)
    if code_match:
        return code_match.group(1)

    # fallback: first 1-3 words initials
    words = re.findall(r'[A-Za-z0-9]+', event_text)
    if words:
        initials = ''.join(w[0].upper() for w in words[:4])
        return initials or "EVENT"

    return ""


def extract_event_display(event_text: str) -> str:
    """
    For games.json 'name' field:
    'WTF World Championship Tournament 2025' -> 'WTF 2025'
    If no caps code exists, fallback to a short readable label.
    """
    code_match = re.search(r'\b([A-Z]{2,})\b', event_text)
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', event_text)

    code = code_match.group(1) if code_match else None
    year = year_match.group(1) if year_match else None

    if code and year:
        return f"{code} {year}"
    if code:
        return code
    if year:
        return f"Event {year}"

    # fallback: first few words
    words = re.findall(r'[A-Za-z0-9]+', event_text)
    return ' '.join(words[:3]) if words else ""


def extract_result_and_win_type(text: str) -> tuple[str, str]:
    """
    Returns:
      result_code for filename: B / W / D / U
      win_type for JSON: e.g. 'B', 'W', 'D', 'W corner'
    """
    # Explicit result lines
    if re.search(r'\bBlack won\.', text, re.IGNORECASE):
        return "B", "B"
    if re.search(r'\bWhite won\.', text, re.IGNORECASE):
        return "W", "W"
    if re.search(r'\bDraw\.', text, re.IGNORECASE):
        return "D", "D"
    return "U", "U"


def extract_datetime(text: str) -> tuple[str | None, str | None, str | None]:
    """
    Finds:
      2025-11-12 11:49:38 (Copenhagen time)

    Returns:
      date_part = '2025-11-12'
      time_part = '114938'
      display_time = '11:49'
    """
    m = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2}):(\d{2})', text)
    if not m:
        return None, None, None

    date_part = m.group(1)
    hh, mm, ss = m.group(2), m.group(3), m.group(4)
    time_part = f"{hh}{mm}{ss}"
    display_time = f"{hh}:{mm}"
    return date_part, time_part, display_time


def parse_game_file(filepath: Path):
    text = filepath.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    event_line = extract_event_line(lines)
    event_text = extract_event_text(event_line)
    event_code = extract_event_code(event_text)
    event_display = extract_event_display(event_text)

    white_raw = None
    black_raw = None
    
    for line in lines:
        if white_raw is None and line.strip().lower().startswith("white:"):
            m = re.match(r'^White:\s*(.+)$', line.strip(), re.IGNORECASE)
            if m:
                white_raw = m.group(1).split(",")[0].strip()
    
        if black_raw is None and line.strip().lower().startswith("black:"):
            m = re.match(r'^Black:\s*(.+)$', line.strip(), re.IGNORECASE)
            if m:
                black_raw = m.group(1).split(",")[0].strip()
    
    white = sanitize_filename_part(white_raw) if white_raw else None
    black = sanitize_filename_part(black_raw) if black_raw else None
    
    white_display = normalize_display_name(white_raw) if white_raw else None
    black_display = normalize_display_name(black_raw) if black_raw else None

    result_code, win_type = extract_result_and_win_type(text)
    date_part, time_part, display_time = extract_datetime(text)

    if not white or not black or not date_part or not time_part or not display_time:
        raise ValueError("Missing required fields (white/black/date/time)")

    # Filename format:
    # White-Black_EventYYYY-MM-DD_HHMMSS_X.txt
    # Example: Casshern-Draganov_WTF2025-11-12_114938_B.txt
    new_filename = f"{white}-{black}_{event_code}{date_part}_{time_part}_{result_code}.txt"

    # JSON display name:
    # "WTF 2025 Casshern-Draganov 2025-11-12 11:49"
    json_name = f"{event_display} {white_display}-{black_display} {date_part} {display_time}"
    
    # Sort key
    dt = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H%M%S")

    entry = {
        "name": json_name,
        "file": new_filename,
        "win_type": win_type
    }

    return {
        "old_path": filepath,
        "new_filename": new_filename,
        "entry": entry,
        "sort_dt": dt
    }


def load_existing_games(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        print(f"WARNING: Could not parse {path.name}, starting from empty list.")
        return []


def extract_sort_dt_from_entry(entry: dict) -> datetime:
    """
    Sort by date embedded in:
    "WTF 2025 Casshern-Draganov 2025-11-12 11:49"
    """
    name = entry.get("name", "")
    m = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2})$', name)
    if m:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}", "%Y-%m-%d %H:%M")
    # fallback if bad format
    return datetime.max


def merge_games(existing: list[dict], new_entries: list[dict]) -> list[dict]:
    """
    Deduplicate by 'file'.
    If an entry already exists with the same filename, KEEP the existing one
    (so manual win_type edits are preserved).
    """
    merged = {}

    for entry in existing:
        file_key = entry.get("file")
        if file_key:
            merged[file_key] = entry

    for entry in new_entries:
        file_key = entry["file"]
        if file_key not in merged:
            merged[file_key] = entry

    games = list(merged.values())
    games.sort(key=extract_sort_dt_from_entry)
9.3    return games


def main():
    txt_files = sorted(FOLDER.glob("*.txt"))
    if not txt_files:
        print("No .txt files found.")
        return

    parsed_entries = []

    for filepath in txt_files:
        # Skip games.json if someone accidentally named it .txt (unlikely)
        if filepath.name.lower() == "games.json":
            continue

        try:
            parsed = parse_game_file(filepath)

            old_path = parsed["old_path"]
            new_filename = parsed["new_filename"]
            new_path = old_path.with_name(new_filename)

            if old_path.name != new_filename:
                if new_path.exists() and new_path.resolve() != old_path.resolve():
                    print(f"SKIP rename (target exists): {old_path.name} -> {new_filename}")
                else:
                    if DRY_RUN:
                        print(f"DRY RUN rename: {old_path.name} -> {new_filename}")
                    else:
                        old_path.rename(new_path)
                        print(f"RENAMED: {old_path.name} -> {new_filename}")
                        parsed["old_path"] = new_path
            else:
                print(f"Already named correctly: {old_path.name}")

            parsed_entries.append(parsed)

        except Exception as e:
            print(f"ERROR parsing {filepath.name}: {e}")

    # Build new JSON entries from parsed files
    new_json_entries = [p["entry"] for p in parsed_entries]

    # Load existing games.json
    existing_games = load_existing_games(GAMES_JSON)

    # Merge + sort
    final_games = merge_games(existing_games, new_json_entries)

    # Write games.json
    if DRY_RUN:
        print("\nDRY RUN games.json preview:")
        print(json.dumps(final_games, indent=2, ensure_ascii=False))
    else:
        with GAMES_JSON.open("w", encoding="utf-8") as f:
            json.dump(final_games, f, indent=2, ensure_ascii=False)
        print(f"\nUpdated {GAMES_JSON.name} with {len(final_games)} total entries.")


if __name__ == "__main__":
    main()