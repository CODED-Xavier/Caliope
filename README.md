# Calíope (v2.0)

Calíope, named after the muse of epic poetry, is a roleplay and tabletop RPG app that runs 100% on your PC: no token limits, no subscription.
In Calíope the game master is **the Aedo** (the singer of the Homeric epics), chapters are **Cantos**, and the AI that helps you write stories and cards is **the Muse**.
It keeps everything it needs in a local SQLite file (`backend/data/rpg.db`).


## 0. Quick start (every time you play)

Double-click **`Play.bat`**. That's it. It:

1. sets up Python packages the first time (and again only when they change),
2. builds the interface when it is missing or its code changed (needs Node.js for that),
3. starts the app,
4. starts LM Studio's server and loads your model with your context size, if they are not running yet,
5. opens **http://127.0.0.1:8000** in your browser.

Keep the black window open while you play; close it to stop. The first run asks whether to put a
**Caliope** shortcut on your desktop (or run `Play.bat --shortcut` any time).

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

## 4i. Built-in AI engine and the Windows program (v1.0)

**Built-in engine (no LM Studio needed).** Settings > Model > AI engine > *Built-in*.
1. Press **Download engine** once (about 30 MB: llama.cpp's official Vulkan build for Windows, from its GitHub releases page; works on AMD cards like the RX 580).
2. Pick the **Story model**. The list shows the .gguf files LM Studio already downloaded (nothing is copied), or paste any .gguf path.
3. Optional: a **Memory search model** (e.g. nomic-embed-text) for search by meaning. It runs as a second small server.
4. Save. The engine loads the model (10 to 60 s) and from then on starts with the app and stops when you close it.
- Close LM Studio's model first (or the two will fight over the 8 GB of video memory).
- If loading fails, open *Engine log*: "out of memory" means lower the **Context window** or set **GPU layers** to a number like 28.
- The engine uses the Context window setting directly, keeps the whole context for the story (one slot), and reuses the unchanged start of the prompt between turns, like LM Studio.
- Ports: 8091 (story) and 8092 (memory search). Change `engine_port` if something else uses them.

**The Windows program.** Run **build-exe.bat** (after Play.bat ran once). It builds the interface, installs PyInstaller the first time, and makes the folder `Caliope\` with **Caliope.exe**.
- The program keeps its own saves in `Caliope\data` (copied from Play.bat's `backend\data` the first time), the engine in `Caliope\engine`, skills in `Caliope\skills`. Rebuilding replaces only the program files, never these folders.
- Double-click Caliope.exe: a window shows the status and the app opens in your browser. Close that window to stop everything (the engine stops with it).
- Copy the whole `Caliope` folder to move it; it needs no Python or Node.js.
- Coming from v1.x? The first build copies your saves and engine from the old `LocalRPG` folder; delete that folder afterwards.

**Models window (🧠 Models in the sidebar).** Like LM Studio's model page, inside the app:
- *My models*: every .gguf on this PC (LM Studio's folder included). **Load** / **Unload** in the built-in engine, **Use for memory** for embedding models, **Deactivate** to hide a model from the lists without deleting it, 🗑 to delete it (asks first; only inside the model folders).
- *Browse this PC*: use models you already have (LM Studio's, or any folder) without downloading them again. **Browse…** opens Windows' file picker (pick any .gguf; its folder is added), or paste a folder's address. Nothing is copied, and LM Studio doesn't need to be open. A moved LM Studio models folder is found automatically.
- *Find more*: searches Hugging Face for GGUF models; open a result to see each size (Q4_K_M, Q4_K_S…) with a short note on quality and whether it fits an 8 GB card.
- *Downloads*: progress and speed; Cancel pauses (Download again resumes), and every file is checked against Hugging Face's published checksum. New models go to LM Studio's folder, so both programs share them.

## 4j. Your world additions (player lorebook)

On the start screen (and later in Journal > *Your world additions*) you can add lore of your own for this game: a great house your character belongs to, a home village, a secret order.
- They are **canon**: the GM is told they are true and win where the card's lore disagrees (a card with five great houses now has six), and to weave them into the world's politics and history.
- One line of each entry is always in the prompt; the full text is added when the entry's name or one of its keywords comes up (like the card's lorebook).
- **✨ New facts from the story** reads the recent story and suggests facts it established about the entry (new members, events); click *Add* on the ones you want, then Save.
- Your character's Background now keeps up to 900 characters in the prompt (was 400); put long details in a lore entry instead.

## 4k. World calendar (card editor > Calendar)

Each card can have its own calendar: week days, months and their lengths, what a month and a year are called, the era, and the date and hour the story starts (presets: our calendar, a fantasy one).
- **The app keeps the clock, not the AI.** The date and hour are shown at the top of the chat and in Journal. After each turn the tracker only estimates how long the scene took (a talk: minutes, a meal: an hour); the app moves the clock, never more than 12 hours in one turn.
- **Days pass only when you choose:** `/wait 2 hours`, `/wait 3 days`, `/wait until Sunday`, `/wait until morning`, or in your own words ("I sleep until morning", "we travel for three days"). What your character *says* (in quotes) never skips time. Undo puts the clock back.
- **Appointments:** "the festival is on Sunday" becomes an appointment on the exact day (counted by the app from the calendar, not by the AI). The GM sees today, the coming week day by day and the appointments, so "in two days" is always right; skipping past an appointment tells you about it. You can add or remove appointments in Journal.
- Needs the tracker (on by default) to move the clock between skips.

## 4l. Done by the app, not the AI (v1.5)

- **Roll buttons:** when the GM asks for a check ("Make a DEX (Stealth) check, DC 13"), a 🎲 button appears under the reply (▲ advantage, ▼ disadvantage). The app adds your sheet's bonus (ability modifier, plus proficiency when the skill or save is on your sheet), rolls, and tells the GM "17 vs DC 13 → ✅ Success".
- **Quiet turns are faster:** on turns of pure talk the tracker (the second AI call after each reply) is skipped and reads those turns together a little later. Money, items, wounds, travel, quests or a new name make it run at once. Settings > *Skip tracking on quiet turns*.
- **INFO status block kept by the app** (cards like Lumencia): place, time, items, money, HP, quests and relationships come from the game; the card's own values (Tier, EXP, Crowns...) start from the opening scene and the tracker reports only what changed. The AI no longer writes the block (faster replies, right numbers). Status tab > *Edit the card's values* to correct them. Card editor > Advanced lets a card go back to "Written by the AI".
- **Weather from the calendar:** with a calendar, the app rolls the day's weather from the season and the card's climate (temperate, cold, warm, tropical, dry, or off). It lasts a day or two and the GM describes it.
- **Shops and money:** prices in a reply ("a lantern (5 gold)") become 🛒 buttons; buying checks your money, takes it and puts the item in your bag. The Bag tab has a **Pay** box. The tracker never counts those twice. Card editor: *Money is called* (gold, crowns...).
- **Quests:** the AI can add quests, but only suggests when one is completed or failed; you confirm it in the Bag tab.
- **Exact prompt size:** the app learns how many characters make one token for your model from the server's real counts, so it keeps as much history as really fits.

## 4m. Resources and powers (Mana, Aura, Stamina...)

Card editor > **Resources and powers**: the card's pools (name, maximum, colour, how they refill: per round, short rest, night, new day; −1 = all of it) and the powers that spend them (attack, heal or effect; cost, damage or healing dice, range). **✨ Suggest from the card** lets the AI propose them for the setting; you change anything.
- The **Sheet** shows bars, the powers with a **Use** button (refused without enough) and **Short rest / Long rest** (with a calendar they pass 1 or 8 hours; a long rest also heals). A game started before you added them: *Get resources and powers from the card*.
- **In fights** the powers are buttons in the Combat tab: the app pays the cost, rolls the hit and damage or the healing, and pools that refill per round do so. Enemy casters (*＋ casts spells* in the fight form, or suggested by the AI) spend from their own pool and fall back to weapons when it runs dry.
- When the story spends a resource without a button ("you pour your aura into the barrier"), the tracker subtracts it. The GM always sees your pools and is told to show a drained character as drained.

## 4n. Its own window

Play.bat and Caliope.exe open the game in a window of its own (Microsoft Edge's app mode, which comes with Windows: no tabs, no address bar), not in a browser tab. The black window is minimized; it still holds the messages and errors. **Closing the game window stops everything.** Settings > *Open in its own window* turns it off (back to a browser tab). If Edge is missing, Chrome or Brave is used, else your normal browser.

## 4o. Starts, characters and pictures (v2.1)
- **👥 Characters**: on a card in the New game list (and on the "Who are you?" screen) shows every character with picture, name and role. Click a picture to zoom.
- **Choose your start**: a card can have several starts. The default is the card's opening; imported alternate openings appear too; the card editor (under *Opening message*) adds full starts: their own opening, how the world is on that route (the Aedo reads it every turn), who the story starts with (everyone else is met in the story) and **fixed scenes** the Aedo plays in order, one per reply (separate them with a line of `---`).
- **Pictures from a folder** (card editor, *Characters*): pick a folder with one subfolder per character holding `1.png`…`6.png` (1 Standard, 2 Happy, 3 Sad, 4 Angry, 5 Disgusted, 6 Blushing), or a single `Name.png`. Names match without caring about capitals, accents or a missing surname; a preview shows what matched and lets you assign the rest by hand. Missing moods use the closest one. The pictures are copied into the app (`data\cardpics`) and also replace them in games already using the card. Run it again whenever you add pictures.
- **Private cloud (Cloudflare R2)**: Settings > *Pictures in the cloud* takes your R2 account ID, bucket and keys; ☁ in the card editor uploads the card's pictures. The bucket stays private: the app signs every download, keeps a copy on this PC, and the card only holds `r2:` links that nobody else can open.

## 4p. The Muse (v2.2)
**🪶 The Muse** (left sidebar) is a writer's room with the same model that plays your games: brainstorm worlds, characters, a new route for a card. Talks are saved; long talks are summarized as they go. **↶ Undo last** removes her last answer to ask differently.
**✨ Make it a card** turns the talk into a card, asking the model for one piece at a time (title, pitch, world, tone, each character's sheet, the opening) so the card always comes out valid. The preview offers **＋ Add to Calíope** (it appears in New game, ✎ to edit) or **⤓ Save file** (a standard Character Card JSON you can import later). It takes one or two minutes on an RX 580. The Muse and a game share the model, so one waits for the other.

## 4q. Cantos, recap and the map bag (v2.3)
- **Cantos** (Journal tab): your story's chapters. *Close this Canto* at a natural break: the Aedo writes a short chronicle, a divider marks the new Canto in the chat, and the chronicles of past Cantos stay in what the Aedo always knows. Rewinding or undoing into a closed Canto opens it again.
- **📜 Recap** (top of the chat): "Previously, in…", written only when you click it and never added to the story.
- **🎒 Map bag** (Map tab): scene pictures you keep, with place, in-game date and Canto. The first picture of each place is kept on its own; 📌 on any scene picture keeps it; click to see it big, ✎ to name it. The Map tab appears for any game with scene pictures.

## 4r. Backups and .caliope card files (v2.4)
- **Daily backups**: once a day all your games, characters, memories and cards are copied to `data\backups\rpg-<date>.db`; the last 7 are kept (Settings > Backups: turn off, change the number, *Back up now*, *Open folder*). To restore: close Calíope, rename `data\rpg.db` (keep it), copy a backup into `data`, rename it `rpg.db`, start again. Pictures from folders and music are files in `data`, not inside the backup.
- **📦 .caliope files**: in the New game list, 📦 saves a card with all its pictures in one file. *Import a card* reads `.caliope` files back (pictures included), so you can share a card with a friend without GitHub or the cloud. Pictures that are only public links stay links.

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
