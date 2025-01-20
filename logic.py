import curses
import random
import sys
import locale
import os
import json
import textwrap

import openai

openai.api_key = os.getenv("OPENAI_API_KEY", None)

locale.setlocale(locale.LC_ALL, '')

WALL_CHAR = "#"
DOOR_CHAR = "/"
FLOOR_CHAR = " "

POSSIBLE_ROOM_NAMES = [
    "Kitchen", "Ballroom", "Conservatory", "DiningRoom", 
    "BilliardRoom", "Library", "Lounge", "Hall", "Study"
]

PLAYER_CHAR = "\U0001F464"  # 👤
victim_data = {
    "name": "Mr. Boddy",
    "emoji": "\U0001F480",  # 💀
    "x": 10,
    "y": 4,
}

suspects_data = [
    {"name": "Mr. Green",    "emoji": "\U0001F468",            "x": 3,  "y": 3},
    {"name": "Ms. Scarlet",  "emoji": "\U0001F469",            "x": 12, "y": 3},
    {"name": "Col. Mustard", "emoji": "\U0001F474",            "x": 3,  "y": 9},
    {"name": "Mrs. Peacock", "emoji": "\U0001F475",            "x": 12, "y": 9},
    {"name": "Prof. Plum",   "emoji": "\U0001F468\U0001F3A8",  "x": 3,  "y": 15},
    {"name": "Dr. Orchid",   "emoji": "\U0001F469\U0001F3EB",  "x": 12, "y": 15},
]

weapons_data = [
    {"name": "Knife",       "emoji": "\U0001F52A", "x": 2,  "y": 3},
    {"name": "Candlestick", "emoji": "\U0001F56F", "x": 13, "y": 3},
    {"name": "Revolver",    "emoji": "\U0001F52B", "x": 2,  "y": 9},
    {"name": "Rope",        "emoji": "\U0001F517", "x": 13, "y": 9},
    {"name": "Lead Pipe",   "emoji": "\U0001F6AC", "x": 2,  "y": 15},
    {"name": "Wrench",      "emoji": "\U0001F527", "x": 13, "y": 15},
]

clues_data = [
    {"text": "Blood stains in the Study",  "x": 3,  "y": 2},
    {"text": "Open window in Library",     "x": 12, "y": 2},
    {"text": "Footprints in the Hall",     "x": 3,  "y": 8},
    {"text": "Broken glass in Lounge",     "x": 12, "y": 8},
    {"text": "Napkin in Dining Room",      "x": 3,  "y": 14},
    {"text": "Knife missing from Kitchen", "x": 12, "y": 14},
]

CLUE_CHAR = "\U0001F4DC"  # 📜

murder_story = "(No full story generated.)"
cryptic_intro = "(No intro)"

chat_history = {}

def generate_story_clues_and_intro(murderer_name, weapon_name, used_room_names):
    """
    Calls ChatGPT to create:
      - A short story about the murder (30-50 words).
      - A short spooky intro (10-20 words).
      - A list of six short textual clues referencing the scenario.
    """
    if not openai.api_key:
        return "(No story - missing OPENAI_API_KEY)", "(No intro)", []

    room_list_str = ", ".join(used_room_names)
    system_prompt = (
        "You are a creative assistant generating a Clue-like murder scenario. "
        "We have a victim named Mr. Boddy, a suspect named MURDERER who used WEAPON as the murder weapon. "
        f"There are these rooms in the mansion: {room_list_str}. "
        "We want three pieces of content in valid JSON:\n"
        "  1) 'story': a short murder scenario (30-50 words)\n"
        "  2) 'intro': a short, spooky, 10-20 word teaser that sets the mood but doesn't reveal who or how\n"
        "  3) 'clues': a list of exactly six short textual clues (5-12 words each).\n"
        "Output must be valid JSON with keys 'story', 'intro', and 'clues'. Do NOT wrap JSON in markdown."
    )

    user_prompt = (
        f"MURDERER = {murderer_name}\n"
        f"WEAPON = {weapon_name}\n"
        "Victim = Mr. Boddy\n"
        "Please provide JSON in the format:\n"
        "{\n"
        "  \"story\": \"...\",\n"
        "  \"intro\": \"...\",\n"
        "  \"clues\": [\"c1\", \"c2\", \"c3\", \"c4\", \"c5\", \"c6\"]\n"
        "}\n"
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=400,
            temperature=0.9
        )
        assistant_text = response["choices"][0]["message"]["content"]
    except Exception as e:
        return (f"(Failed to generate story via ChatGPT: {e})", "(No intro)", [])

    story_text = "(No story parsed)"
    intro_text = "(No intro parsed)"
    clues_list = []
    try:
        data = json.loads(assistant_text)
        story_text = data.get("story", "(No story field)")
        intro_text = data.get("intro", "(No intro field)")
        clues_list = data.get("clues", [])
        if not isinstance(clues_list, list):
            clues_list = []
    except json.JSONDecodeError:
        story_text = "(Could not parse JSON.)"
        intro_text = "(Could not parse JSON.)"
        clues_list = []

    return story_text, intro_text, clues_list

def generate_game_map(num_rooms, overall_width, overall_height):
    """
    Dynamically generate a game map with the specified number of rooms.
    """
    grid = [[WALL_CHAR for _ in range(overall_width)] for _ in range(overall_height)]
    cols = 2
    rows = (num_rooms + cols - 1) // cols
    room_width = overall_width // cols
    room_height = overall_height // rows

    rooms = []
    count = 0
    selected_room_names = POSSIBLE_ROOM_NAMES[:num_rooms]

    for r in range(rows):
        for c in range(cols):
            if count >= num_rooms:
                break

            x = c * room_width + 1
            y = r * room_height + 1
            room_inner_width = room_width - 2
            room_inner_height = room_height - 2
            room_name = selected_room_names[count]

            rooms.append({
                'name': room_name,
                'center_x': x + room_inner_width // 2,
                'center_y': y + room_inner_height // 2,
                'x1': x,
                'y1': y,
                'x2': x + room_inner_width - 1,
                'y2': y + room_inner_height - 1
            })

            for row in range(y, y + room_inner_height):
                for col in range(x, x + room_inner_width):
                    if 0 <= row < overall_height and 0 <= col < overall_width:
                        grid[row][col] = FLOOR_CHAR

            if c > 0: 
                door_y = y + room_inner_height // 2
                grid[door_y][x - 1] = DOOR_CHAR
                grid[door_y][x - 2] = DOOR_CHAR
            if r > 0:
                door_x = x + 15
                row_above = y - 1
                if 0 <= row_above < len(grid) and 0 <= door_x < len(grid[0]):
                    grid[row_above][door_x] = DOOR_CHAR
                    grid[row_above-1][door_x] = DOOR_CHAR

            top_wall_y = y - 1
            top_wall_x = x
            for i, ch in enumerate(room_name):
                if (0 <= top_wall_y < overall_height and
                    0 <= (top_wall_x + i) < overall_width):
                    grid[top_wall_y][top_wall_x + i] = ch

            count += 1

    map_data = ["".join(row) for row in grid]
    return map_data, rooms, selected_room_names

def is_valid_tile(game_map, x, y):
    rows = len(game_map)
    cols = len(game_map[0]) if rows > 0 else 0
    if 0 <= y < rows and 0 <= x < cols:
        return game_map[y][x] != WALL_CHAR
    return False

def find_suspect_at(x, y):
    for s in suspects_data:
        if s["x"] == x and s["y"] == y:
            return s
    return None

def find_weapon_at(x, y):
    for w in weapons_data:
        if w["x"] == x and w["y"] == y and "collected" not in w:
            return w
    return None

def find_clue_at(x, y):
    for c in clues_data:
        if c["x"] == x and c["y"] == y and "found" not in c:
            return c
    return None 