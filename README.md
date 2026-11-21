# Calíope

**Calíope** (named after the muse of epic poetry) is a roleplay and tabletop RPG app that runs entirely on your PC.
There are no token limits and no subscription, and your stories never leave your computer.

Inside Calíope:
- the game master is **the Aedo**, the singer of the Homeric epics
- the chapters of a story are **Cantos**
- the AI that helps you write stories and cards is **the Muse**

Current version: **v2.6**. The version history is at the end of this file.

**Beta testers:** start with [BETA-TESTERS.md](BETA-TESTERS.md), a step-by-step guide to install, play and report bugs.

---

## Contents
1. [Quick start](#1-quick-start)
2. [The AI model](#2-the-ai-model)
3. [Playing a game](#3-playing-a-game)
4. [Cards](#4-cards)
5. [The Muse](#5-the-muse)
6. [Pictures, music and voice](#6-pictures-music-and-voice)
7. [How the Aedo remembers](#7-how-the-aedo-remembers)
8. [Rulebooks and skills](#8-rulebooks-and-skills)
9. [Your data, backups and privacy](#9-your-data-backups-and-privacy)
10. [The Windows program (Caliope.exe)](#10-the-windows-program-caliopeexe)
11. [Settings worth knowing](#11-settings-worth-knowing)
12. [Troubleshooting](#12-troubleshooting)
13. [For developers](#13-for-developers)
14. [Version history](#14-version-history)

---

## 1. Quick start

**You need this once:**
- [Python 3.12](https://www.python.org/) (tick "Add Python to PATH"), or run `py install 3.12` in PowerShell
- [Node.js LTS](https://nodejs.org/), used only to build the interface

**Every time you play:** double-click **`Play.bat`**. It:
1. installs the Python packages the first time (and again only when they change)
2. builds the interface when it is missing or its code changed
3. starts the app, plus the AI (the built-in engine, or LM Studio if you use it)
4. opens Calíope in **its own window**: no browser tabs, no address bar

The black window is minimized; it holds messages and errors. **Closing the game window stops everything.**
The first run offers a **Caliope** desktop shortcut (or run `Play.bat --shortcut` any time).

Options: `Play.bat --no-browser`, `Play.bat --no-lmstudio`.

Before your first game, give it a model ([section 2](#2-the-ai-model)).

---

## 2. The AI model

Calíope works with a local roleplay model. On an 8 GB graphics card (such as the RX 580), a good choice is
**L3-8B-Stheno-v3.2** in **Q4_K_M** or **Q4_K_S** (about 5 GB).

### Option A: the built-in engine (recommended; no LM Studio)
1. Sidebar → **🧠 Models**.
2. **Download engine** (about 30 MB): llama.cpp's official Vulkan build, which works on AMD cards.
3. Get a model:
   - *Browse this PC*: use models you already have, such as LM Studio's, without copying them. **Browse…** opens Windows' file picker, or you can paste a folder's address.
   - *Find more*: search Hugging Face. Each file size has a note on quality and on whether it fits 8 GB. Downloads resume after a pause and are checked against Hugging Face's checksums.
4. *My models* → **Load**. Optionally, **Use for memory** on a small embedding model (e.g. `nomic-embed-text`) for memory search by meaning.

The engine starts with the app and stops when you close it.
- If loading fails with "out of memory", lower the **Context window** or set **GPU layers** to about 28 in Settings.
- Close LM Studio's own model first, so the two don't fight over video memory.

### Option B: LM Studio
In LM Studio:
1. Choose the **Vulkan** runtime (Settings > Runtime).
2. Load the model with **Context length 8192** and **GPU offload: max**.
3. Start the **local server**.

In Calíope: Settings > AI engine > *LM Studio*, address `http://localhost:1234/v1`. Play.bat can start LM Studio's server for you.

### Online services
Settings > *API key* also works with services that speak the same language (OpenRouter, for example): put their address in *Server address* and your key in *API key*. Remember that they see your story, charge per use, and may refuse dark scenes.

---

## 3. Playing a game

### Starting
1. **＋ New game** → pick a card. 👥 shows its characters with picture, name and role.
2. If the card has several starts, choose one in **Choose your start** (for example, Lumencia's default start or another route).
3. **Create your sheet** (Adventure cards) or **Who are you?** (Roleplay cards).
   - Or choose *Let the story ask me* for cards that create your character in the chat.
   - **✨ Fill the empty fields** suggests a background, looks and personality.
   - **Your world additions**: lore of your own (a great house, a home village, a secret order). It is canon in this game, even where the card says otherwise.
   - **🎭 Personas**: pick one of your saved characters to fill this screen, or **💾 Save as persona** to reuse this one in other games (name, background, looks, personality and world additions).

### How to write
| You write | Meaning |
|---|---|
| `"Hello there."` | Your character speaks |
| `*I draw my sword*` | Your character acts |
| `'He is lying.'` | Your character thinks. Only the Aedo knows (characters never do) and may give subtle hints. |
| `/how much gold do I have?` | A message to the Aedo outside the story |
| `/roll 1d20+3` | Dice, rolled by the app (`adv`, `dis`, `4d6kh3` work too) |
| `/wait 3 days`, `/wait until morning` | Time passes, only when you choose |
| no marks | The Aedo decides |

The message box checks your spelling as you type (red underline; right-click for suggestions), in the story's language.

### Under the replies
- **Continue ▸**: keeps writing the same reply. **↻ Regenerate**: writes it again.
- **↶ Undo**, **edit** or **re-send** a message, and **⏪ rewind** to any point. Sheet, money, HP, dice and the clock go back too.
- **⑂ Save point**: a new game from that moment; the original is not changed.
- **🎲 roll buttons** appear when the Aedo asks for a check ("DEX (Stealth), DC 13"). The app adds your sheet's bonus and rolls.
- **🛒 buy buttons** appear for prices in a reply. The app checks your money and puts the item in your bag.
- **🔊** reads the reply aloud (needs a voice, [section 6](#6-pictures-music-and-voice)).
- **🖼** paints the scene; **📌** keeps a picture in the map bag.

### At the top of the chat
- **📜 Recap**: "Previously, in…", written only when you ask and never added to the story.
- **🎵 Music**, **🔍 search** (Ctrl+F), **⤓ export** to Markdown.
- **Aa**: text size, wider column, compact mode, story colours (grey narration, bright speech, coloured thoughts), character picture size, follow the text as it is written.
- The **date and hour** of the story.

### The side panel
Tabs appear when the card uses them. Drag the panel's edge to resize it. The small **‹ ›** bubbles on the chat's edges hide the games list or the panel completely, giving the story the whole window; click them again to bring the columns back.
- **Sheet**: HP, attributes, money, place, time and weather, resource bars (Mana, Aura…), powers with **Use**, short and long rest.
- **Bag**: items, quests (when a quest seems finished, you confirm it), **Pay** box.
- **People**: everyone you have met, with relationships from −100 to +100. Characters count as met only when they actually interact with you.
  - **Notes** under each character: yours (what you think of them, a promise, a debt), plus the Aedo's own, marked ✒, which he adds after important moments ("promised to train the player at dawn"). The Aedo keeps them in mind whenever that character is in the scene; edit or delete any line.
- **Status**: the card's INFO block, kept by the app (cards like Lumencia).
- **Map**: places, plus the **🎒 map bag** of kept scene pictures.
- **⚔ Combat**: fights with a battle map ([below](#combat)).
- **Dice** and **Journal**: Cantos, the pinned memory box, summary, memories, calendar appointments, your world additions.

### Cantos (chapters)
Journal → **Close this Canto** at a natural break. The Aedo writes a short chronicle, a divider marks the new Canto in the
chat, and the chronicles of past Cantos stay in what the Aedo always knows. Rewinding into a closed Canto opens it again.

### Time and the calendar
Each card can have its own calendar (card editor > Calendar). **The app keeps the clock, not the AI.**
- Scenes move the clock by minutes or hours. **Days pass only when you choose** (`/wait`, or "I sleep until morning").
- Appointments ("the festival is on Sunday") land on the exact day.
- The weather comes from the season and the card's climate.

### Combat
⚔ Combat → choose **d20** (D&D 5e) or a **d10 dice pool** (Vampire 5e) → add enemies, or **✨ Suggest from the scene** → pick a map → **Start the fight**.
- The app rolls everything (initiative, attacks, damage, powers, enemy spells). The Aedo only narrates one ⚔️ card per round.
- Maps: generated (forest, dungeon, tavern, river…) or your own from **🗺 My maps**. Walls block, obstacles give **cover**, and mud and bushes slow you.
- Undo and rewind also undo the dice.

### Resources and powers
Card editor > **Resources and powers**: pools (Mana, Aura, Stamina…) with maximum, colour and refill (per round, rest, night, day), and powers that spend them.
- The Sheet and Combat tabs have **Use** buttons; the app pays the cost and rolls.
- When the story spends a resource without a button ("you pour your aura into the barrier"), the tracker subtracts it.

---

## 4. Cards

A card is a world to play: its rules, setting, characters and opening.
- **Roleplay** cards are simple and fast: characters, relationships, conversation.
- **Adventure** cards add rules, items, quests, maps and combat.

The AI's role:
- **Aedo · open world**: invents places and people as you go.
- **Aedo · preset cast**: runs the characters you define.
- **One character**: the AI plays a single character; the story is about your relationship.

### Making and editing cards
- **＋ New game → ✎** on a card opens the editor. **✨ Write with AI** drafts the teaser, world, rules, tone or opening from the rest of the card.
- **✨ Generate from an idea** drafts a whole card. The [Muse](#5-the-muse) goes further.
- **Characters**: description, personality, speech style, looks, pictures and moods.

### Importing and sharing
- **Import a card** reads Character Card V2 JSON files (the SillyTavern format), the lorebook included, and **.caliope** files.
  - Lorebook entries reach the Aedo only when their keywords come up, so 30+ characters don't fill the prompt.
  - Characters listed in the lorebook become people with portraits.
- **📦** in the card list saves a **.caliope** file: the card **with all its pictures**, to share without GitHub or the cloud.
- **⤓** saves a standard JSON card (pictures stay as links).

### Starts (routes)
A card can be entered in different ways. In the card editor, under *Opening message*, **Starts** can each have:
- their own opening
- **how the world is on this route** (the Aedo reads it every turn)
- **who the story starts with**: everyone else is met in the story
- **fixed scenes**, played one per reply in order and adapted to what you do (separate them with a line of `---`)

### Character pictures from a folder
Card editor > *Characters* → **📂 Pick the pictures folder…** (or paste its address). The layout:
```
pictures\
  Artemis\1.png 2.png 3.png 4.png 5.png 6.png
  Lilia\1.png
  Bishop Corvin.png
```
- `1` Standard, `2` Happy, `3` Sad, `4` Angry, `5` Disgusted, `6` Blushing (or the card's own mood names).
- A single `Name.png` is used as the Standard picture.
- Folder names match characters without caring about capitals, accents or a missing surname.
- A preview shows what matched. Unmatched folders get a list: pick the character by hand, or **＋ Add as a new character** (the folder's name becomes a new character of the card, also added to games already using it). Nothing changes until **Apply**.
- Missing moods use the closest one (Disgusted → Angry, Blushing → Happy, otherwise Standard).
- The pictures are copied into Calíope and also update games already using the card. Run it again whenever you finish more pictures.

### Private cloud pictures (Cloudflare R2), optional
1. Settings > *Pictures in the cloud*: R2 account ID, bucket, access key and secret.
2. Card editor → **☁ Upload this card's pictures**.

The bucket stays private: Calíope signs every download with your keys and keeps a copy on this PC. The card only holds `r2:` links that nobody else can open.

---

## 5. The Muse

**🪶 The Muse** (left sidebar) is a writer's room with the same model that plays your games.
- Brainstorm worlds, characters, a new route for a card, a twist for your campaign. Talks are saved, and long talks are summarized as they go.
- **↶ Undo last** removes her last answer so you can ask differently.
- **✨ Make it a card** turns the talk into a card. The model is asked for one piece at a time (title, pitch, world, tone, each character's sheet, the opening), so the card always comes out valid. It takes one or two minutes on an RX 580.
- The preview offers **＋ Add to Calíope** (find it in New game; ✎ to edit) or **⤓ Save file** (a JSON card to import later).

The Muse and your games share the model, so one waits for the other.

---

## 6. Pictures, music and voice

### Character pictures and moods
People tab or card editor → *🖼 Pictures and moods*: a main picture plus Standard, Happy, Sad, Angry, Disgusted, Blushing, and up to 12 moods of your own. Each comes from your PC (⬆) or a link (🔗).
- The Aedo shows a character's picture above the part where they speak, and the picture changes with their mood.
- **Your own picture**: click the circle beside your name on the Sheet.

### Scene pictures and the map bag (optional, needs internet)
Settings > *Scene pictures*. When a scene starts (a new place, a fight), the Aedo describes the place and a picture is painted above the reply.
- **Pollinations** (free, no account) is the default. **PixAI** can be used with your own API key and model ID.
- Only the description of the place leaves your PC: names are removed and your messages are never sent.
- **🎒 Map bag** (Map tab): the first picture of each place is kept on its own, and **📌** keeps any other. Each shows the place, in-game date and Canto.

### Jukebox
**🎵 Music** → add songs from your PC (or direct audio links) and tag them with moods (tavern, forest, dungeon, combat, boss, victory…).
With **Auto**, the music follows the scene: combat music in fights, boss music for bosses, a victory song when you win.

### Narration voice
Settings > *Narration voice*:
1. Download the voice program (Piper, about 25 MB) and a voice (about 60 MB each): Lessac, Amy, Ryan (English US), Alan (English UK) or **Faber** (Português do Brasil).
2. Pick it as *Voice for 🔊*.
3. **🔊** on any reply reads it aloud (⏹ stops), or turn on *Read every new reply aloud*.

It runs on the processor, so the story model keeps the graphics card. Each reply is read once and kept.

### Themes
Black, violet and orange. The dark theme (☾) leads with violet and the light theme with orange.

---

## 7. How the Aedo remembers

The model can only read a limited amount of text at once (the **context window**, usually 8192 tokens), so Calíope layers memory:

| Layer | What it holds |
|---|---|
| Recent rounds | The last ~10 exchanges, word for word (adjustable) |
| **Cantos** | A chronicle of every closed chapter |
| Summary | A rolling summary of older events |
| Memories | Important facts, found again by keywords or by meaning when they matter |
| Pinned memory box | Up to 2,000 characters you write; always included |
| Game state | Sheet, bag, quests, relationships, clock, resources: kept by the app |
| Lorebooks | The card's and yours, added when their keywords come up |

After each reply a short second call (the **tracker**) notes what changed. On quiet turns of pure talk it is skipped and catches up later.

---

## 8. Rulebooks and skills

**📚 Rules** → import a PDF or text rulebook, then tick it in a card's *Rulebooks*.
- When a turn touches a rule (grappling, falling, frenzy…), the Aedo gets the matching section, and **📖 Rules used** shows which.
- **House rules** win over the book.
- Scanned books need the free [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki).
- A good free start: the **D&D System Reference Document 5.2**.

**🧩 Skills** are folders with a `SKILL.md` (style guides, genre advice). Install them in the Skills window and attach up to 3 to a card. Skill scripts are never run.

---

## 9. Your data, backups and privacy

Everything lives in `backend\data` (with Play.bat) or `Caliope\data` (with the exe):

| Item | Where |
|---|---|
| Games, cards, characters, memories, settings | `rpg.db` |
| Daily backups | `backups\rpg-<date>.db` |
| Pictures (uploads, downloads, card folders) | `portraits\`, `cardpics\` |
| Music | `music\` |
| Voice program, voices and spoken replies | `voice\` |

**Backups:** once a day everything in `rpg.db` is copied to `backups`, and the last 7 days are kept (Settings > Backups: *Back up now*, *Open folder*, how many days).
To restore:
1. Close Calíope.
2. Rename `rpg.db` (keep it).
3. Copy a backup into `data` and rename it `rpg.db`.
4. Start Calíope again.

**What goes online, and only if you turn it on:**
- scene picture descriptions (Pollinations or PixAI)
- R2 uploads and downloads
- downloads of the engine, models and voices from their official sites
- an online model, if you set one

Everything else stays on this PC. Calíope only answers on this PC (127.0.0.1) and refuses requests from other websites.

---

## 10. The Windows program (Caliope.exe)

Run **`build-exe.bat`** (after Play.bat ran once). It builds the folder `Caliope\` with **Caliope.exe**, which needs no Python or Node.js.
- Its saves are in `Caliope\data`, the engine in `Caliope\engine`, skills in `Caliope\skills`. Rebuilding replaces only the program files, never these folders.
- The first build copies your saves from `backend\data` (and from the old `LocalRPG` folder of v1.x; delete that folder afterwards).
- Copy the whole `Caliope` folder to move it. An installer is planned.

---

## 11. Settings worth knowing

| Setting | What it does |
|---|---|
| AI engine | Built-in (llama.cpp) or LM Studio / another server |
| Context window | How much text the model reads at once; must match the model (8192) |
| Reply length | Short, medium or long replies |
| Rounds kept word for word | How many recent exchanges stay complete |
| Track the sheet automatically | The tracker after each reply (turn off for speed) |
| Skip tracking on quiet turns | Faster talk scenes |
| Summarize old messages | The rolling summary |
| Scene pictures / Painted by | Pictures for new scenes; Pollinations or PixAI |
| Narration voice | Piper voice, speed, read every reply |
| Backups | Daily copy, days to keep |
| Open in its own window | App window or a normal browser tab |

Every setting has a **?** with a short explanation.

---

## 12. Troubleshooting

| Problem | Try |
|---|---|
| "Cannot reach the model server" | Built-in engine: 🧠 Models → Load a model. LM Studio: start its server, and check that *Server address* is `http://localhost:1234/v1`. |
| Engine: out of memory | Lower *Context window* or set *GPU layers* to ~28. Close LM Studio's model. |
| Replies are slow | *Reply length*: short. Turn on *Skip tracking on quiet turns*. Fewer *rounds kept*. |
| The interface looks old after an update | Close the game window and run Play.bat again (it rebuilds the interface). |
| A picture doesn't show | Links can break; use 📂 pictures from a folder or ⬆ from your PC. |
| Something else | The black window (open it from the taskbar) shows the error; copy it when asking for help. |

---

## 13. For developers

Calíope is a FastAPI + SQLite backend (`backend/app`) that serves a React + Vite interface (`frontend`).
`AGENTS.md` explains the layout and the rules that keep the app working.

- **Development mode** (the interface reloads as you edit): `start-backend.bat` and `start-frontend.bat`, then http://localhost:5173.
- **Tests**: no GPU, network or LM Studio needed (a fake model is used).
  ```
  cd backend
  python -m unittest discover -s tests -t .
  ```
- **API**: http://127.0.0.1:8000/docs lists every endpoint. Turns stream as server-sent events (`user_message`, `token`, `assistant_message`, `state`, `done`, `error`…).
- Each feature lives on its own branch with tests and a version tag.

---

## 14. Version history

| Version | What came |
|---|---|
| 0.2 | Backend and web interface |
| 0.3 | Edit, rewind, delete and re-send messages |
| 0.4 | Speed and memory: pinned memory box, rounds window, reply length |
| 0.5 | Roleplay and Adventure cards, skills as add-ons, character looks |
| 0.6 | Character card import with lorebook, big portraits, Status tab, Continue |
| 0.7 | Start screens, writing marks, time and weather, Aa menu, search, export, save points |
| 0.8 | Pictures beside messages, moods and the mood editor |
| 0.9 | One-click `Play.bat` |
| 0.10 | Rulebooks with OCR, search and house rules |
| 0.11 | Combat with dice by code, battle maps, terrain and cover |
| 0.12 | Jukebox |
| 0.13 | Scene pictures |
| 1.0 | Built-in llama.cpp engine and the Windows program |
| 1.1 | Models window (Hugging Face search, downloads, load and unload) |
| 1.2 | Your world additions (player lorebook) |
| 1.3 | World calendar with real time |
| 1.4 | Code audit: performance, security and fixes |
| 1.5 | The app does the counting: checks, shop, INFO block, quiet turns |
| 1.6 | Resources and powers |
| 1.7 | Its own window |
| 1.8 | Story colours |
| 1.9 | Collapsible sidebars, big pictures, the "met" fix |
| 1.10 | Audit leftovers: faster memory search, re-send undoes old results, upload limits |
| 1.11 | The pixel-art icon |
| 1.12 | Browse this PC for models |
| **2.0** | **Calíope**: new name, violet and orange themes, API key, PixAI option |
| 2.1 | Card starts (routes), character preview, pictures from a folder, private R2 |
| 2.2 | The Muse |
| 2.3 | Cantos, recap, map bag |
| 2.4 | Daily backups and .caliope card files |
| 2.5 | Narration voice |
| 2.6 | Columns hide fully, no scrollbars, spell check, character notes (yours and the Aedo's), Personas, new characters from a picture folder |
