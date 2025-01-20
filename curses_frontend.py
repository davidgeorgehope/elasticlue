import curses
import textwrap
import random
import sys

import openai
from logic import (
    PLAYER_CHAR, CLUE_CHAR, FLOOR_CHAR, WALL_CHAR, DOOR_CHAR,
    victim_data, suspects_data, weapons_data, clues_data,
    murder_story, cryptic_intro, chat_history,
    generate_story_clues_and_intro, generate_game_map,
    is_valid_tile, find_suspect_at, find_weapon_at, find_clue_at,
    POSSIBLE_ROOM_NAMES
)

def chat_with_suspect(stdscr, suspect, is_murderer):
    """
    Simple chat loop using ChatGPT in curses.
    """
    suspect_name = suspect["name"]
    if suspect_name not in chat_history:
        chat_history[suspect_name] = []

    system_message = (
        f"You are {suspect_name}, a Clue-like murder suspect in a text-based game.\n"
        "Mr. Boddy has been found murdered.\n"
    )
    if is_murderer:
        system_message += (
            "Secretly, you DO know you are the murderer. Respond in character but don't be too obvious. "
            "When presented with enough evidence you might have to come clean.\n"
        )
    else:
        system_message += (
            "You do not know who the murderer is (because it isn't you). "
            "Stay in character as an innocent suspect.\n"
        )
    system_message += (
        "Answer the player's questions in a fun, story-driven way.\n"
        "Be concise. Keep responses under 50 words.\n"
    )

    def build_messages():
        msgs = [{"role": "system", "content": system_message}]
        for item in chat_history[suspect_name]:
            msgs.append(item)
        return msgs

    curses.echo()
    while True:
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()
        stdscr.addstr(0, 0, f"Chatting with {suspect_name} (type 'q' alone to quit)")

        HISTORY_LINES = 10
        displayed_history = chat_history[suspect_name][-HISTORY_LINES:]
        offset = 2
        for entry in displayed_history:
            role = entry["role"].capitalize()
            text = entry["content"]
            combined_line = f"{role}: {text}"
            wrapped = textwrap.wrap(combined_line, max_x - 1)
            for line in wrapped:
                if offset >= max_y - 2:
                    break
                stdscr.addstr(offset, 0, line)
                offset += 1

        input_y = max_y - 1
        prompt = "Your message (Enter='send', 'q' alone='quit'): "
        prompt_show = prompt[:max_x-1]
        stdscr.addstr(input_y, 0, prompt_show)
        stdscr.move(input_y, len(prompt_show))
        stdscr.refresh()

        raw_input = stdscr.getstr(input_y, len(prompt_show), max_x - len(prompt_show) - 1)
        if not raw_input:
            continue

        user_msg = raw_input.decode("utf-8", errors="ignore").strip()
        if user_msg.lower() == 'q' and len(user_msg) == 1:
            break

        chat_history[suspect_name].append({"role": "user", "content": user_msg})

        try:
            if not openai.api_key:
                ai_text = "(No OPENAI_API_KEY configured.)"
            else:
                resp = openai.ChatCompletion.create(
                    model="gpt-4o",
                    messages=build_messages(),
                    max_tokens=100,
                    temperature=0.9
                )
                ai_text = resp["choices"][0]["message"]["content"]
        except Exception as e:
            ai_text = f"(OpenAI error: {e})"

        chat_history[suspect_name].append({"role": "assistant", "content": ai_text})

    curses.noecho()

def view_clues(stdscr, collected_clues):
    """
    A separate page for clues, so they don't clutter main UI.
    Press 'Q' or ESC to exit.
    """
    curses.curs_set(0)
    while True:
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()
        stdscr.addstr(0, 0, "Collected Clues (press 'Q' or ESC to return)")

        offset = 2
        if not collected_clues:
            stdscr.addstr(offset, 0, "(No clues yet)")
        else:
            for clue in collected_clues:
                prefix = "- "
                wrapped_lines = textwrap.wrap(prefix + clue, max_x - 1)
                for line in wrapped_lines:
                    if offset >= max_y - 1:
                        break
                    stdscr.addstr(offset, 0, line)
                    offset += 1

        stdscr.refresh()
        k = stdscr.getch()
        if k in [ord('q'), ord('Q'), 27]:
            break

def reveal_full_story(stdscr, murder_story):
    """
    Displays the entire ChatGPT-generated murder story.
    """
    curses.curs_set(0)
    while True:
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()
        title = "The Full Story"
        stdscr.addstr(0, 0, title)

        wrapped_lines = textwrap.wrap(murder_story, max_x - 1)
        offset = 2
        for line in wrapped_lines:
            if offset >= max_y:
                break
            stdscr.addstr(offset, 0, line)
            offset += 1

        if offset < max_y:
            stdscr.addstr(offset, 0, "(Press any key to exit)")
        stdscr.refresh()

        key = stdscr.getch()
        if key != -1:
            break

def select_weapon(stdscr, inventory):
    """
    Displays a small list of weapons in your inventory and
    lets you pick one using arrow-key navigation and Enter.
    """
    if len(inventory) == 1:
        return inventory[0]

    idx = 0
    while True:
        stdscr.clear()
        stdscr.addstr(0, 0, "Select a weapon (↑/↓ to navigate, Enter to confirm, Q to cancel):")

        for i, w in enumerate(inventory):
            highlight = ">> " if i == idx else "   "
            stdscr.addstr(i + 2, 0, f"{highlight}{w}")

        stdscr.refresh()
        key = stdscr.getch()

        if key in (ord('q'), ord('Q'), 27):
            return None
        elif key == curses.KEY_DOWN:
            idx = (idx + 1) % len(inventory)
        elif key == curses.KEY_UP:
            idx = (idx - 1) % len(inventory)
        elif key in (curses.KEY_ENTER, 10, 13):
            return inventory[idx]

def main(stdscr, game_map, rooms, selected_room_names):
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)

    global murder_story
    global cryptic_intro

    player_x, player_y = 2, 2
    inventory = []
    collected_clues = []
    game_message = "Use arrow keys to move. Press 'C' to chat, 'A' to accuse, 'L' for clues."

    murderer = random.choice(suspects_data)
    murder_weapon = random.choice(weapons_data)

    new_story, new_intro, new_clues = generate_story_clues_and_intro(
        murderer["name"],
        murder_weapon["name"],
        selected_room_names
    )

    murder_story = new_story
    cryptic_intro = new_intro

    for i, clue_text in enumerate(new_clues):
        if i < len(clues_data):
            clues_data[i]["text"] = clue_text

    while True:
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        map_rows = len(game_map)
        map_cols = len(game_map[0]) if map_rows > 0 else 0
        ui_lines = 8
        available_height = max_y - ui_lines
        if available_height <= 0 or map_cols == 0 or map_rows == 0:
            stdscr.addstr(0, 0, "Terminal too small. Enlarge window.")
            stdscr.refresh()
            c = stdscr.getch()
            if c in [ord('q'), ord('Q'), 27]:
                break
            continue

        tile_height = max(1, available_height // map_rows)
        tile_width = max(1, max_x // map_cols)

        for row in range(map_rows):
            for col in range(map_cols):
                tile = game_map[row][col]
                draw_char = tile if tile != FLOOR_CHAR else " "
                screen_y = row * tile_height
                screen_x = col * tile_width
                try:
                    stdscr.addstr(screen_y, screen_x, draw_char)
                except:
                    pass

        try:
            vy = victim_data["y"] * tile_height - 1
            vx = victim_data["x"] * tile_width - 1
            stdscr.addstr(vy, vx, victim_data["emoji"])
        except:
            pass

        for w in weapons_data:
            if "x" in w and "y" in w and "collected" not in w:
                sy = w["y"] * tile_height
                sx = w["x"] * tile_width
                try:
                    stdscr.addstr(sy, sx, w["emoji"])
                except:
                    pass

        for c_data in clues_data:
            if "x" in c_data and "y" in c_data and "found" not in c_data:
                sy = c_data["y"] * tile_height
                sx = c_data["x"] * tile_width
                try:
                    stdscr.addstr(sy, sx, CLUE_CHAR)
                except:
                    pass

        for s in suspects_data:
            if "x" in s and "y" in s:
                sy = s["y"] * tile_height
                sx = s["x"] * tile_width
                try:
                    stdscr.addstr(sy, sx, s["emoji"])
                except:
                    pass

        py = player_y * tile_height
        px = player_x * tile_width
        stdscr.addstr(py, px, PLAYER_CHAR)

        ui_start = map_rows * tile_height
        intro_lines = textwrap.wrap(f"Intro: {cryptic_intro}", width=max_x - 1)
        used_ui_lines = 0
        for line in intro_lines:
            if ui_start + used_ui_lines >= max_y:
                break
            stdscr.addstr(ui_start + used_ui_lines, 0, line)
            used_ui_lines += 1

        if ui_start + used_ui_lines < max_y:
            stdscr.addstr(ui_start + used_ui_lines, 0,
                          f"INVENTORY: {', '.join(inventory) if inventory else '(empty)'}")
            used_ui_lines += 1

        if ui_start + used_ui_lines < max_y:
            stdscr.addstr(ui_start + used_ui_lines, 0, f"MESSAGE: {game_message}")
            used_ui_lines += 1

        if ui_start + used_ui_lines < max_y:
            stdscr.addstr(ui_start + used_ui_lines, 0, "Press 'Q' or ESC to quit.")
            stdscr.addstr(ui_start + used_ui_lines + 1, 0, "Use arrow keys to move. Press 'C' to chat, 'A' to accuse, 'L' for clues.")
            used_ui_lines += 2

        stdscr.refresh()

        c = stdscr.getch()
        if c in [ord('q'), ord('Q'), 27]:
            break

        new_x, new_y = player_x, player_y
        if c == curses.KEY_LEFT:
            new_x -= 1
        elif c == curses.KEY_RIGHT:
            new_x += 1
        elif c == curses.KEY_UP:
            new_y -= 1
        elif c == curses.KEY_DOWN:
            new_y += 1
        elif c in (ord('a'), ord('A')):
            suspect_here = find_suspect_at(player_x, player_y)
            if not suspect_here:
                game_message = "No suspect here to accuse!"
            else:
                if not inventory:
                    game_message = "No weapons in inventory."
                else:
                    chosen_weapon = select_weapon(stdscr, inventory)
                    if not chosen_weapon:
                        game_message = "Accusation canceled."
                    else:
                        if (suspect_here["name"] == murderer["name"]
                                and chosen_weapon == murder_weapon["name"]):
                            game_message = f"Correct! {suspect_here['name']} with the {chosen_weapon}. YOU WIN!"
                            reveal_full_story(stdscr, murder_story)
                            break
                        else:
                            game_message = (f"Wrong! Suspect: {suspect_here['name']} / "
                                            f"Weapon: {chosen_weapon}. Try again!")
        elif c in (ord('c'), ord('C')):
            suspect_here = find_suspect_at(player_x, player_y)
            if not suspect_here:
                game_message = "No suspect here to chat with!"
            else:
                is_murderer = (suspect_here["name"] == murderer["name"])
                chat_with_suspect(stdscr, suspect_here, is_murderer)
                game_message = "You finished chatting."
        elif c in (ord('l'), ord('L')):
            view_clues(stdscr, collected_clues)

        if new_x != player_x or new_y != player_y:
            if is_valid_tile(game_map, new_x, new_y):
                player_x, player_y = new_x, new_y
                w_item = find_weapon_at(player_x, player_y)
                if w_item:
                    w_item["collected"] = True
                    inventory.append(w_item["name"])
                    game_message = f"You picked up {w_item['name']}!"
                clue_item = find_clue_at(player_x, player_y)
                if clue_item:
                    clue_item["found"] = True
                    collected_clues.append(clue_item["text"])
                    game_message = f"You found a clue: \"{clue_item['text']}\""

    stdscr.nodelay(False)
    stdscr.clear()
    stdscr.addstr(0, 0, "Thanks for playing! Press any key to exit.")
    stdscr.refresh()
    stdscr.getch()

if __name__ == "__main__":
    try:
        num_rooms = 6
        overall_width = 40
        overall_height = 15
        generated_map, rooms, selected_room_names = generate_game_map(num_rooms, overall_width, overall_height)

        # Distribute suspects, weapons, clues among rooms
        for i, (suspect, weapon, clue) in enumerate(zip(suspects_data, weapons_data, clues_data)):
            if i < len(rooms):
                rm = rooms[i]
                suspect["x"] = rm['x1'] + 2
                suspect["y"] = rm['center_y']
                weapon["x"] = rm['x2'] - 2
                weapon["y"] = rm['center_y']
                clue["x"] = rm['center_x']
                clue["y"] = rm['y1'] + 1

        curses.wrapper(main, generated_map, rooms, selected_room_names)
    except KeyboardInterrupt:
        sys.exit(0) 