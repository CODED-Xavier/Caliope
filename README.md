# Local RPG Chat (v0.6: character card import)

A chatbot for RPG and roleplay that runs 100% on your PC: no token limits, no subscription.
It keeps everything it needs in a local SQLite file (`backend/data/rpg.db`).


## 0. Quick start (every time you play)

1. Open **LM Studio**, load the model and switch the local server on.
2. Double-click **`start-backend.bat`** (keep that window open).
3. Double-click **`start-frontend.bat`**. The first run installs packages (needs internet), then your browser opens
   at **http://localhost:5173**. This mode reloads automatically when the code changes.

Prefer a single window? Double-click **`build-frontend.bat`** once, then only run `start-backend.bat`
and open **http://127.0.0.1:8000**. (Run the build again after any interface change.)

Needs: Python 3.12 (`py install 3.12`) and Node.js LTS.

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
