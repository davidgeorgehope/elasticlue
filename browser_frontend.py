import random
import json
from flask import Flask, request, render_template_string, redirect, url_for, jsonify
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

app = Flask(__name__)

# ------------------------------------------------------------------------------
# Slightly bigger map + tile size for better room display
# ------------------------------------------------------------------------------
player_x, player_y = 2, 2
inventory = []
collected_clues = []

murderer = random.choice(suspects_data)
murder_weapon = random.choice(weapons_data)

num_rooms = 6
overall_width = 40
overall_height = 15
game_map, rooms, selected_room_names = generate_game_map(num_rooms, overall_width, overall_height)

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

new_story, new_intro, new_clues = generate_story_clues_and_intro(
    murderer["name"],
    murder_weapon["name"],
    selected_room_names
)

# At the top, add/modify a global variable to store the current game message
game_message = "Welcome to the mansion! Search for clues—and do be careful…"

@app.route("/")
def index():
    """
    Renders the main canvas page.
    Now includes an invisible chat overlay that we toggle with the 'C' key.
    Also includes a server message at the top, which can update dynamically.
    """
    # Make sure we use the global message here
    global game_message

    game_data = {
        "intro": new_intro,
        "message": game_message,  # <--- Use the global message
        "mapWidth": overall_width,
        "mapHeight": overall_height,
        "player": {"x": player_x, "y": player_y},
        "victim": {"x": victim_data["x"], "y": victim_data["y"], "emoji": victim_data["emoji"]},
        "suspects": [
            {"x": s["x"], "y": s["y"], "emoji": s["emoji"], "name": s["name"]}
            for s in suspects_data
        ],
        "weapons": [
            {
                "x": w["x"],
                "y": w["y"],
                "emoji": w["emoji"],
                "name": w["name"],
                "collected": w.get("collected", False)
            }
            for w in weapons_data
        ],
        "clues": [
            {"x": c["x"], "y": c["y"], "found": c.get("found", False)}
            for c in clues_data
        ],
        "gameMap": game_map
    }
    game_data_json = json.dumps(game_data)
    
    # Inline JS/HTML for the basic page + canvas + chat overlay
    html_content = f"""
    <html>
      <head>
        <title>Clue Game - Canvas Version</title>
        <style>
          body {{
            font-family: Arial, sans-serif;
          }}
          #gameCanvas {{
            border: 2px solid #000;
            background-color: #eee;
          }}
          /* Basic overlay styling for chat */
          #chatOverlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            display: none; /* hidden by default */
            justify-content: center;
            align-items: center;
          }}
          .chat-box {{
            background: #fff;
            padding: 20px;
            width: 400px;
            border-radius: 8px;
          }}
          .chat-log {{
            height: 200px;
            overflow-y: auto;
            border: 1px solid #ccc;
            padding: 5px;
            margin-bottom: 10px;
          }}
        </style>
      </head>
      <body>
        <h1>Clue Game (Canvas)</h1>Intro: {new_intro}

           <p>Use Arrow keys to move. Press 'C' to chat with suspect.</p>

        <p>
          <a href="/clues">View Collected Clues</a> |
          <a href="/accuse">Accuse a Suspect</a> |
          <a href="/story">Full Story</a> |
          <a href="/quit">Quit</a>
        </p>     

        <!-- Display the dynamic server message -->
        <p><strong>Message:</strong> {game_data["message"]}</p>

        <canvas id="gameCanvas"></canvas>


        <!-- Chat overlay -->
        <div id="chatOverlay">
          <div class="chat-box">
            <!-- A title that shows who we're chatting with -->
            <h2 id="chatTitle"></h2>
            <div class="chat-log" id="chatLog"></div>
            <form id="chatForm">
              <input type="text" id="chatInput" placeholder="Say something..." size="40"/>
              <button type="submit">Send</button>
            </form>
            <button type="button" onclick="hideChat()">Close</button>
          </div>
        </div>

        <script>
          var gameData = {game_data_json};
          var TILE_SIZE = 32;
          var mapWidth = gameData.mapWidth;
          var mapHeight = gameData.mapHeight;

          // Set up canvas
          var canvas = document.getElementById("gameCanvas");
          canvas.width = mapWidth * TILE_SIZE;
          canvas.height = mapHeight * TILE_SIZE;
          var ctx = canvas.getContext("2d");
          ctx.font = "16px sans-serif";

          function drawTile(tile, x, y) {{
            if (tile === "{WALL_CHAR}") {{
              ctx.fillStyle = "darkgray";
              ctx.fillRect(x, y, TILE_SIZE, TILE_SIZE);
            }} else if (tile === "{DOOR_CHAR}") {{
              ctx.fillStyle = "brown";
              ctx.fillRect(x, y, TILE_SIZE, TILE_SIZE);
            }} else if (tile === "{FLOOR_CHAR}") {{
              ctx.fillStyle = "lightgray";
              ctx.fillRect(x, y, TILE_SIZE, TILE_SIZE);
            }} else {{
              // For room letters
              ctx.fillStyle = "white";
              ctx.fillRect(x, y, TILE_SIZE, TILE_SIZE);
              ctx.fillStyle = "black";
              ctx.fillText(tile, x + 8, y + 20);
            }}
          }}

          function drawEverything() {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            var mapData = gameData.gameMap;
            for (var row = 0; row < mapHeight; row++) {{
              for (var col = 0; col < mapWidth; col++) {{
                drawTile(mapData[row][col], col * TILE_SIZE, row * TILE_SIZE);
              }}
            }}

            // Victim
            ctx.fillStyle = "red";
            ctx.fillText(gameData.victim.emoji,
                         gameData.victim.x * TILE_SIZE + 8,
                         gameData.victim.y * TILE_SIZE - 10);

            // Suspects
            for (var i = 0; i < gameData.suspects.length; i++) {{
              var s = gameData.suspects[i];
              ctx.fillStyle = "blue";
              ctx.fillText(s.emoji,
                           s.x * TILE_SIZE + 8,
                           s.y * TILE_SIZE + 20);
            }}

            // Weapons
            for (var i = 0; i < gameData.weapons.length; i++) {{
              var w = gameData.weapons[i];
              if (!w.collected) {{
                ctx.fillStyle = "green";
                ctx.fillText(w.emoji,
                             w.x * TILE_SIZE + 8,
                             w.y * TILE_SIZE + 20);
              }}
            }}

            // Clues
            for (var i = 0; i < gameData.clues.length; i++) {{
              var c = gameData.clues[i];
              if (!c.found) {{
                ctx.fillStyle = "purple";
                ctx.fillText("{CLUE_CHAR}",
                             c.x * TILE_SIZE + 8,
                             c.y * TILE_SIZE + 20);
              }}
            }}

            // Player
            ctx.fillStyle = "black";
            ctx.fillText("{PLAYER_CHAR}",
                         gameData.player.x * TILE_SIZE + 8,
                         gameData.player.y * TILE_SIZE + 20);
          }}

          drawEverything();

          // Movement + Chat
          window.addEventListener("keydown", function(e) {{
            var key = e.key;
            if (key === "ArrowLeft") {{
              window.location = "/move?dx=-1&dy=0";
            }} else if (key === "ArrowRight") {{
              window.location = "/move?dx=1&dy=0";
            }} else if (key === "ArrowUp") {{
              window.location = "/move?dx=0&dy=-1";
            }} else if (key === "ArrowDown") {{
              window.location = "/move?dx=0&dy=1";
            }} else if (key === "c" || key === "C") {{
              e.preventDefault();
              openChatIfSuspect();
            }}
          }});

          function openChatIfSuspect() {{
            fetch("/check_suspect")
              .then(resp => resp.json())
              .then(data => {{
                if (data.hasSuspect) {{
                  showChat(data.suspectName, data.chatHtml);
                }} else {{
                  alert("No suspect here to chat with!");
                }}
              }});
          }}

          // show/hide chat overlay
          function showChat(suspectName, chatHtml) {{
            document.getElementById("chatTitle").textContent = "Chat with " + suspectName;
            document.getElementById("chatLog").innerHTML = chatHtml;
            document.getElementById("chatOverlay").style.display = "flex";
          }}
          function hideChat() {{
            document.getElementById("chatOverlay").style.display = "none";
          }}

          // handle chat form submission via AJAX
          var chatForm = document.getElementById("chatForm");
          chatForm.addEventListener("submit", function(e) {{
            e.preventDefault();
            var userMsg = document.getElementById("chatInput").value.trim();
            if (!userMsg) return;
            fetch("/chat_ajax", {{
              method: "POST",
              headers: {{
                "Content-Type": "application/json"
              }},
              body: JSON.stringify({{user_msg: userMsg}})
            }})
            .then(resp => resp.json())
            .then(data => {{
              document.getElementById("chatLog").innerHTML = data.chatHtml;
              document.getElementById("chatInput").value = "";
            }});
          }});
        </script>
      </body>
    </html>
    """
    return html_content

@app.route("/move")
def move_player():
    """
    Moves the player and updates the global message
    when picking up weapons or clues.
    """
    global player_x, player_y, game_message

    dx = int(request.args.get("dx", 0))
    dy = int(request.args.get("dy", 0))
    new_x = player_x + dx
    new_y = player_y + dy

    if is_valid_tile(game_map, new_x, new_y):
        player_x, player_y = new_x, new_y

        w_item = find_weapon_at(player_x, player_y)
        if w_item and not w_item.get("collected", False):
            w_item["collected"] = True
            inventory.append(w_item["name"])
            # Update the message
            game_message = f"You picked up {w_item['name']}!"

        clue_item = find_clue_at(player_x, player_y)
        if clue_item and not clue_item.get("found", False):
            clue_item["found"] = True
            collected_clues.append(clue_item["text"])
            # Update the message
            game_message = f"You found a clue: '{clue_item['text']}'"

    return redirect(url_for("index"))

@app.route("/check_suspect")
def check_suspect():
    """
    Returns JSON saying if we have a suspect at player location.
    If so, also returns the suspect name and current chat message HTML.
    """
    suspect_here = find_suspect_at(player_x, player_y)
    if not suspect_here:
        return jsonify({"hasSuspect": False})
    suspect_name = suspect_here["name"]
    
    # Build the existing chat log
    # If no chat for them yet, it's blank
    history_txt = []
    if suspect_name in chat_history:
        for entry in chat_history[suspect_name]:
            speaker = entry['role'].capitalize()
            content = entry['content']
            history_txt.append(f"<b>{speaker}:</b> {content}")
    joined_history = "<br>".join(history_txt)
    
    return jsonify({
        "hasSuspect": True,
        "suspectName": suspect_name,
        "chatHtml": joined_history
    })

@app.route("/chat_ajax", methods=["POST"])
def chat_ajax():
    """
    Receives a user_msg for the suspect at the current player position,
    does the normal ChatGPT logic, then returns fresh HTML for the chat log.
    """
    data = request.json
    user_msg = data.get("user_msg", "").strip()
    suspect_here = find_suspect_at(player_x, player_y)
    if not suspect_here:
        return jsonify({"chatHtml": "(No suspect here!)"})

    suspect_name = suspect_here["name"]
    if suspect_name not in chat_history:
        chat_history[suspect_name] = []
    if user_msg:
        chat_history[suspect_name].append({"role": "user", "content": user_msg})

    is_murderer = (suspect_name == murderer["name"])
    system_message = (
        f"You are {suspect_name}, a Clue-like murder suspect.\n"
        "Mr. Boddy has been found murdered.\n"
    )
    if is_murderer:
        system_message += "Secretly, you DO know you are the murderer. Respond in character but don't be too obvious.\n"
    else:
        system_message += "You are not the murderer.\n"
    system_message += "Answer the player's question in a fun, story-driven way, under 50 words."

    msgs = [{"role": "system", "content": system_message}]
    for item in chat_history[suspect_name]:
        msgs.append(item)

    ai_text = "(No OPENAI_API_KEY configured.)"
    if openai.api_key:
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=msgs,
                max_tokens=100,
                temperature=0.9
            )
            ai_text = resp["choices"][0]["message"]["content"]
        except Exception as e:
            ai_text = f"(OpenAI error: {e})"

    chat_history[suspect_name].append({"role": "assistant", "content": ai_text})

    # Build updated log
    history_txt = []
    for entry in chat_history[suspect_name]:
        speaker = entry['role'].capitalize()
        content = entry['content']
        history_txt.append(f"<b>{speaker}:</b> {content}")
    joined_history = "<br>".join(history_txt)

    return jsonify({"chatHtml": joined_history})

@app.route("/clues")
def show_clues():
    clue_text = "<br>".join(collected_clues) if collected_clues else "(No clues yet!)"
    return render_template_string(f"""
    <html>
      <head>
        <title>Collected Clues</title>
      </head>
      <body>
        <h1>Collected Clues</h1>
        <p>{clue_text}</p>
        <p><a href="/">Back</a></p>
      </body>
    </html>
    """)

@app.route("/accuse", methods=["GET", "POST"])
def accuse():
    if request.method == "POST":
        suspect_chosen = request.form.get("suspect")
        weapon_chosen = request.form.get("weapon")
        if suspect_chosen and weapon_chosen:
            if suspect_chosen == murderer["name"] and weapon_chosen == murder_weapon["name"]:
                return render_template_string(f"""
                <html><body>
                <h1>YOU WIN!</h1>
                <p>The murderer was {suspect_chosen} with the {weapon_chosen}!</p>
                <p><a href="/story">View Full Story</a></p>
                <p><a href="/">Back</a></p>
                </body></html>
                """)
            else:
                return render_template_string(f"""
                <html><body>
                <h1>WRONG ACCUSATION!</h1>
                <p>You accused {suspect_chosen} with the {weapon_chosen} and failed.</p>
                <p><a href="/">Back</a></p>
                </body></html>
                """)
        else:
            return redirect(url_for("index"))
    else:
        suspect_options = [s["name"] for s in suspects_data]
        weapon_options = [w["name"] for w in weapons_data if w.get("collected")]
        suspect_html = "".join([f"<option value='{n}'>{n}</option>" for n in suspect_options])
        weapon_html = "".join([f"<option value='{w}'>{w}</option>" for w in weapon_options])

        return render_template_string(f"""
        <html>
          <head><title>Accuse</title></head>
          <body>
            <h1>Accuse a suspect</h1>
            <form method="POST">
              <p>Suspect:
                <select name="suspect">
                  {suspect_html}
                </select>
              </p>
              <p>Weapon (only ones you collected):
                <select name="weapon">
                  {weapon_html}
                </select>
              </p>
              <p><input type="submit" value="Accuse"></p>
            </form>
            <p><a href="/">Back</a></p>
          </body>
        </html>
        """)

@app.route("/story")
def story():
    global new_story
    return render_template_string(f"""
    <html>
      <head><title>Story</title></head>
      <body>
        <h1>The Full Story</h1>
        <p>{new_story}</p>
        <p><a href="/">Back</a></p>
      </body>
    </html>
    """)

@app.route("/quit")
def quit_game():
    sys.exit(0)

if __name__ == "__main__":
    for i, clue_text in enumerate(new_clues):
        if i < len(clues_data):
            clues_data[i]["text"] = clue_text
    app.run(debug=True, port=5001) 