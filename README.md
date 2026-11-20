# Local RPG Chat (v0.13: scene pictures)

A chatbot for RPG and roleplay that runs 100% on your PC: no token limits, no subscription.
It keeps everything it needs in a local SQLite file (`backend/data/rpg.db`).


## 0. Quick start (every time you play)

Double-click **`Play.bat`**. That's it. It:

1. sets up Python packages the first time (and again only when they change),
2. builds the interface when it is missing or its code changed (needs Node.js for that),
3. starts the app,
4. starts LM Studio's server and loads your model with your context size, if they are not running yet,
5. opens **http://127.0.0.1:8000** in your browser.

Keep the black window open while you play; close it to stop. The first run asks whether to put a
**Local RPG** shortcut on your desktop (or run `Play.bat --shortcut` any time).

Options: `Play.bat --no-browser` (don't open the browser), `Play.bat --no-lmstudio` (don't touch LM Studio).

Needs: Python 3.12 (`py install 3.12`), Node.js LTS (only to build the interface) and LM Studio.

**For development** (the interface reloads as you edit the code): run `start-backend.bat` and
`start-frontend.bat`, then open http://localhost:5173.

### What the interface has
- Sidebar with your games, new-game picker (3 example scenarios, your own, or "generate from an idea")
- Streaming chat with markdown, Stop, Regenerate, Undo
- Side panel: **Sheet** (HP, abilities, gold, location), **Bag** (items, quests), **People** (relationship -100 to +100, personality),
  **Map** (places the story names), **Dice**, **Journal** (story summary and long-term memories)
- Settings (model, creativity, language, extra instructions) and Skills manager
- Light and dark themes

## 1. Install (once)

1. Install **Python 3.12** from python.org (tick "Add Python to PATH").
2. Install **LM Studio** from lmstudio.ai.
3. Double-click `start-backend.bat`. The first run creates the environment and installs the packages.
   Open http://127.0.0.1:8000/docs to see the API.

## 2. Set up the model in LM Studio

Your PC (RX 580 8GB) cannot run DeepSeek's large models, so use a smaller roleplay model.

1. In LM Studio, open **Discover** and search for **`L3-8B-Stheno-v3.2`** (GGUF).
   Download the **Q4_K_M** file (about 5 GB). It is a roleplay-focused 8B model that fits your 8GB GPU.
   (Alternative to try later: a Qwen3.5 9B uncensored GGUF. Reasoning "think" text is hidden automatically.)
2. Open **Settings > Runtime** and choose the **Vulkan** llama.cpp runtime (the RX 580 has no ROCm support on Windows).
3. Open the **Developer** tab, load the model and set:
   - **Context length: 8192**
   - **GPU offload: maximum** (all layers). If LM Studio crashes or runs out of memory, lower the context to 6144 or turn Flash Attention off.
4. Start the **local server** (Developer tab, "Start server"). Default address: `http://localhost:1234`.
5. Optional but recommended: also download a small embedding model (search `nomic-embed-text`) and load it.
   Then set `embedding_model` in the app settings (see below). Without it, memory and skill search still work using keywords.

Check the connection: http://127.0.0.1:8000/api/health  should show `"ok": true` and your model name.
Put that exact model name in the `model` setting (`PUT /api/settings {"model": "..."}`).

## 3. How it works

- **Scenarios** define a game: mode, rules, world, cast, player template. Three modes:
  `gm_world` (AI is the GM and invents everything), `gm_cast` (AI is the GM with your preset NPCs), `character` (AI plays one character; the story is about your relationship).
  Three examples are installed on first run. `POST /api/scenarios/generate` drafts a new one from an idea.
- **Memory** has four layers: full chat history (never deleted), a rolling summary of older events,
  the game state (HP, gold, inventory, quests, places) and searchable long-term memories pulled back automatically.
- **State tracking**: after each reply the model is asked, in a second short call, what changed
  (HP, items, relationships from -100 to +100...). All changes are validated in code. Turn it off with `state_tracking: false` if replies feel slow.
- **Dice** are rolled by the program. Type `/roll 1d20+5` (also `adv`/`dis`, `4d6kh3`) in the chat, or call `POST /api/dice/roll`.
- **Skills** are folders with a `SKILL.md`. Put them in `backend/skills/` or install them from the API
  (`POST /api/skills/install` with a folder path, GitHub link or .zip link). In `auto` mode the best matches for each message are
  added to the prompt for that turn. With no skills installed everything works the same. Skill scripts are never executed.
- **Regenerate / undo** restore HP, items and relationships to how they were before that reply.

## 4. Important settings (`GET/PUT /api/settings`)

| Setting | Meaning |
|---|---|
| `model` | Exact model id from LM Studio (`/api/models`) |
| `context_window` | Must match the context length loaded in LM Studio (8192) |
| `max_tokens` | Maximum length of each reply |
| `response_language` | `en`, `pt-BR` or `auto` |
| `embedding_model` | Embedding model id, enables semantic memory/skill search |
| `extra_instructions` | Text added to every prompt (your own style rules) |
| `state_tracking` | Extra call after each turn to update the sheet and memories |

## 4b. Importing character cards (v0.6)

New game → **Import a card** → choose a `.json` file (Character Card V2, the SillyTavern format, or a card exported from this app with ⤓).

- **Card texts** (description, scenario, personality, reminders, example messages) are kept in their own fields. Edit them with ✎ → *Card texts*. `{{user}}` becomes your character's name.
- **Lorebook**: entries are added to the AI's notes only when one of their keywords appears in the last few messages. Entries marked *Always* are always included.
- **Characters** listed in the lorebook (`- Name (…): … Base URL: …`) become NPCs with portraits. Their profile reaches the AI through the lorebook, so 30+ characters do not fill the prompt. The People tab shows the ones you have met; the rest are under *Not met yet*.
- **Portraits**: the AI writes `[[show: Name | Mood]]` and the app shows a big picture above that part of the reply (max 2 per reply). Garbled image links from the AI are fixed by name and mood. Each picture is downloaded once and kept in `backend/data/portraits`.
- **Status block**: if the card asks for an `INFO` block, it is hidden from the story, shown in the **Status** tab and requested only every N replies (3 by default).
- **Relationships** always use the app's -100 to +100 scale, even if the card describes another one.
- **Continue ▸** under the last reply makes the AI keep writing the same reply.

## 4c. Playing (v0.7)

**How to write** (shown under the message box):

| You write | Meaning |
|---|---|
| `"Hello there."` | Your character speaks |
| `*I draw my sword*` | Your character acts |
| `'He is lying.'` | Your character thinks: only the GM knows it, characters never do. The GM may give subtle hints from it. |
| `/how much gold do I have?` | A message to the GM outside the story |
| `/roll 1d20+3` | Rolls dice |
| no marks | The GM decides |

Thoughts are never read by the tracker and never stored as memories.

- **Start screen**: after picking a card, *Create your sheet* (adventure) or *Who are you?* (roleplay). Or choose *Let the story ask me* for cards that create the character in the chat. *✨ Fill the empty fields* suggests a background, looks and personality.
- **✨ Write with AI** in the card editor drafts the teaser, world, rules, tone or opening from the rest of the card.
- The GM keeps track of the **time of day and weather** (also on the Sheet tab).
- **Scrolling**: the view stops at the start of each new reply. *↓ Latest* jumps to the end. To follow the text as it is written, turn it on in **Aa**.
- **Aa** menu: text size, wider column, compact mode. Drag the left edge of the side panel to resize it.
- **🔍** (or Ctrl+F) searches the story. **⤓** exports it as a Markdown file.
- **⑂ Save point** on any message starts a new game from that moment (sheet, characters and memories as they were). The original game is not changed.

## 4d. Pictures and moods (v0.8)

- **Your picture**: click the circle next to your name on the Sheet tab. It shows beside your messages.
- **Character pictures**: open a character in the People tab (or in the card editor) → *🖼 Pictures and moods*. There is a main picture plus Standard, Happy, Sad, Angry, Disgusted and Blushing. Each slot takes a picture from your PC (⬆) or a link (🔗). Empty moods use the main picture. **＋ Add mood** creates a mood with your own name (Smug, Crying, Scared…, up to 12 per character); the AI is told about it.
- **Emotions**: on character cards the character's picture sits beside every reply and changes with the mood of that reply (the AI starts each reply with `[[show: Name | Mood]]`). On Game Master cards the pictures appear above the part where each character speaks.
- **Aa → Character pictures**: Big, Small (a name chip) or Hidden.
- Pictures from your PC are saved in `backend/data/portraits/uploads`. Pictures from links are downloaded once into `backend/data/portraits`.

## 4e. Rulebooks (v0.10)

1. Sidebar → **📚 Rules** → **Import PDF or text**. A PDF with selectable text works best; a `.txt` or `.md`
   file also works (lines starting with `#` become headings). Big books take a minute; progress is shown.
2. Open a card with ✎ → **Rulebooks** and tick the books it uses.
3. Play. When a turn touches a rule (grappling, falling, frenzy…), the GM gets the one or two matching sections
   (about 350 tokens at most). Under the reply, **📖 Rules used** shows which ones.

- **House rules** (button on each book) are sent every turn and win over the book.
- **Look something up** in the Rulebooks window searches all your books.
- **Scanned books** (pages that are pictures) need the free [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
  installed. Restart the app afterwards. OCR takes about 2 to 4 seconds per page.
- If you set an embedding model in Settings, books are also searched by meaning, not only by words.
- Good free start: the **D&D System Reference Document 5.2** (Creative Commons), a PDF on dndbeyond.com.

## 4f. Combat (v0.11)

Side panel → **⚔ Combat** (Adventure cards show it always; any card shows it during a fight).

1. Choose the rules: **d20** (D&D 5e) or **d10 dice pool** (Vampire 5e).
2. Add enemies, or press **✨ Suggest from the scene**: the AI reads the last messages and fills them in. Check the numbers.
   Your own numbers come from your sheet (change them for this fight if needed).
3. **Start the fight.** The app rolls initiative and places everyone on the map.
4. Each round: **Attack** (pick a target, normal/advantage/disadvantage), **Dodge**, or **Something else** (a spell, a trick…).
   The app rolls your action and every other combatant's, updates HP and conditions, and sends the GM one ⚔️ line
   with the exact results. The GM only narrates them: one reply per round.
- Click a token to select it (enemies become your target), then click an empty square to move it (distance in squares and feet).
- **−/＋** changes HP by hand; select a fighter to toggle conditions (prone, grappled, poisoned…), which change advantage.
- **Others act** lets everyone else act now; **End fight** stops it. The fight also ends by itself when one side is down.
- Your HP on the sheet always follows the fight. **Undo/rewind also undo the dice.**

**Maps and terrain:** in the start form choose **Generate** (open field, forest, dungeon, cave, tavern, river crossing,
town street, plus extra rocks/trees/bushes/barrels/water/mud, 🎲 reroll), **one of my maps**, or an empty grid.
✨ Suggest also picks the map type for the scene. **🗺 My maps / editor** lets you paint your own maps (walls, trees,
rocks, crates, water, mud, bushes, doors), optionally over a picture, and save them in a library.
- Walls, trees, rocks, crates and deep water block movement. Something solid between attacker and target gives
  **cover** (+2 AC, or +1 defense die). Standing in bushes also gives cover. Mud and bushes are difficult terrain.
- Enemies walk around obstacles (6 squares a turn) to reach you; enemies with a **Range** above 1 shoot from afar.

**What the chat shows:** one ⚔️ card per round, each action as its own block: who attacks whom, then 🎲 the roll,
then 💥 the damage. The GM then narrates the actions in the same order.

**d20 rules:** attack = d20 + bonus vs AC; natural 20 always hits and doubles the damage dice; natural 1 always misses.
**Dice pool rules:** each d10 of 6+ is a success, each pair of 10s adds 2; attacks are contested by the defender's
pool, and damage = margin + weapon bonus.

## 4g. Jukebox (v0.12)

Background music that follows the story. Click **🎵 Music** in the top bar to open the library.

1. Pick the moods for the songs you are about to add (calm, tavern, exploration, town, forest, dungeon, mystery,
   tension, combat, boss, victory, sad, romantic, horror, epic), then **Add songs from this PC** (MP3, OGG, WAV,
   FLAC, M4A, up to 40 MB each), or paste a **direct audio link**. YouTube/Spotify pages cannot be played.
2. Change a song's moods any time by clicking the chips. **Only for cards** limits a song to some cards; those songs
   are preferred in that card's games.
3. In the top bar: ▶/⏸, ⏭ next, the song and the current mood, volume (hover the player) and **Auto**.

With **Auto** on, the tracker names the mood of each scene and the player fades into a matching song. Fights play
**combat** music (**boss** music when the enemy sounds like a boss), and a won fight plays a **victory** song once.
When no song has a mood, a close one is used (tavern → town → calm…). Browsers only start sound after your first
click, so press ▶ once per session. Songs from your PC are copied into `backend/data/music`.

## 4h. Scene pictures (v0.13, optional, needs internet)

Settings → **Scene pictures (internet)**. When a new scene starts (the first reply of a game, a new place, a fight),
the AI writes a short description of the place and the free **Pollinations.ai** service paints it above the reply.
**🖼** under any GM reply paints that scene; **🎲** on a picture makes another version; **✕** hides it.

- Only the description of the place leaves your PC: names are removed and your messages are never sent.
- The free service paints one picture at a time, about one a minute (the app waits its turn), up to 768×432 here,
  with a small logo in the corner. It may refuse some dark scenes.
- **Picture style** (in Settings) is added to every description: e.g. *oil painting*, *anime style*, *dark gothic illustration*.
- Pictures are kept on your PC after the first time; the **Aa → Character pictures: Hidden** option hides them too.

## 5. Tests

```
cd backend
python -m unittest discover -s tests -v
```
The tests use a fake model, so they need no GPU or LM Studio.

## 6. Main API (the frontend will use these)

- `POST /api/conversations {scenario_id}` start a game; `GET /api/conversations/{id}` load it
- `POST /api/conversations/{id}/chat {content}` streams events (SSE): `user_message`, `context`, `token`, `assistant_message`, `analysis_start`, `state`, `summary`, `done`, `error`
- `POST /api/conversations/{id}/regenerate`, `POST /api/conversations/{id}/undo`
- `GET/PATCH /api/conversations/{id}/state`, `.../npcs`, `.../memories`, `.../memories/search?q=`
- `GET/POST/PUT/DELETE /api/scenarios`, `POST /api/scenarios/generate`
- `GET /api/skills`, `POST /api/skills/install`, `PATCH /api/skills/{name} {enabled}`
