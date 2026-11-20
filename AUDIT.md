# Auditoria: code review (v1.0, November 2026)

Scope: the whole backend (FastAPI, SQLite, prompts, engine, memory, rulebooks, images, built-in engine, model downloads,
calendar) and the main frontend paths (chat streaming, settings, models, journal). Each finding was checked against the code,
and every fix has a regression test (`backend/tests/test_audit.py`, plus `test_worldtime.py` for the undo bug).

## Fixed

| # | Area | Problem | Fix |
|---|------|---------|-----|
| 1 | Performance (high) | Every reply stored a full copy of the sheet and all characters (undo data) inside the message's `meta`. Every read of the chat parsed all of them: 4–6 full reads per turn, plus the chat reload after each turn. A long game with a big card (dozens of NPCs with portrait lists) meant megabytes of JSON per turn, growing with every message. | Undo data now lives in its own compressed column (`messages.snapshot`, zlib, ~10x smaller) and is only read by undo, rewind, regenerate and save points. Old databases are migrated automatically on start. |
| 2 | Performance (high) | While the AI wrote, every message in the chat was redrawn about 60 times a second. The memoized messages received new function objects on each render, so the memo never held. Long chats got sluggish while streaming. | The chat now hands stable functions to the messages, so only the reply being written is redrawn. |
| 3 | Performance (medium) | Rulebook search by meaning computed cosine similarity in pure Python over every passage of every attached book, and read all their texts, on every turn. That's ~0.3–0.6 s per turn for a full PHB. The player's message was also embedded twice per turn (memories and rules). | Vectors are compared with numpy, and only the best passages' texts are read. Both searches use the same query, and a small cache embeds it only once. |
| 4 | Performance (low) | Per-turn checks (status-block timing, tracker context, first scene picture) re-read the whole chat. The games list parsed every game's full card copy. | Small SQL queries now (`COUNT`, `LIMIT`, `json_extract`). SQLite now runs with `synchronous=NORMAL` (safe with WAL), so writes are faster. |
| 5 | Security (medium) | The app answered requests with any `Host` header. A web page could point its own domain at 127.0.0.1 ("DNS rebinding") and read or change your games. Other websites could also send upload requests to the app. | The middleware only answers to `127.0.0.1` / `localhost`. Requests that change something and come from another website's origin are refused. |
| 6 | Security (medium) | Portrait downloads checked the link, then followed redirects without checking them again. A card's portrait link could redirect into your home network. The whole file was also loaded into memory before the 8 MB limit was checked. | Every redirect hop is validated, the download stops at 8 MB, and the image type is read from the bytes, not from the server's label. An HTML page labelled as PNG is refused. |
| 7 | Bug (medium) | **Undo** did not restore the state changed *before* your message. So undoing a combat action kept its dice results (HP lost, enemy turns), and undoing a `/wait` kept the time skip. | Undo restores it (fixed while building the calendar). |
| 8 | Bug (medium) | Changing the embedding model (or adding one later) left every older memory and rulebook passage without vectors for it, so search by meaning silently found nothing old. | On start and whenever the embedding model changes, the app embeds what is missing in the background, once the model server answers. |
| 9 | Bug (medium) | Undo, deleting a game, editing the sheet and adding/removing appointments were accepted while a reply was being written. The running turn then overwrote the change or wrote into a deleted game. | Refused with "Wait for the current reply to finish". |
| 10 | Bug (low) | A save point made just before a fight action or time skip included that action's effects. | The save point uses the first undo data after the message, whichever message carries it. |
| 11 | Bug (low) | A rulebook being read when the app closed stayed "processing" forever. | Marked as interrupted on start, with instructions. |
| 12 | Bug (low) | Matching tracker names to characters used substrings: "Al" matched "Albert", so relationship changes could land on the wrong NPC. | Whole-word matching ("Varro" still finds "Captain Varro"). |
| 13 | Bug (low) | A number like `1e999` from the model crashed the tracker step. | Treated as 0. |
| 14 | Bug (low) | The tracker could crash with an index error if no exchange qualified (an edge after interrupted replies). | Guarded. |
| 15 | Prompt (medium) | With a calendar, the core rules still told the GM to "let time pass naturally with travel, rest and long scenes", which contradicts the calendar rules. | With a calendar on, that rule is replaced by "keep time consistent with the GM notes". |
| 16 | Prompt efficiency (medium) | With a card like Lumencia, the fixed part of the prompt was ~4,400 of 8,192 tokens, leaving room for only 3–4 exchanges of history. About 630 of those tokens were the card's *example messages*, which only matter until the story has its own style. | Example messages are sent for the first 6 replies only, which frees ~300–800 tokens per turn for history. |
| 17 | Built-in engine | The engine log was appended forever, read whole every 1.5 s by the settings window, and a file handle leaked on each restart. | One log per start (the previous one is kept as `engine.log.1`), only the last 8 KB is read, and the handle is closed. |

## Not changed (noted for later)

- **Token estimate:** the app estimates ~3.4 characters per token. That's safe, but ~15% pessimistic for English with Llama-3 tokenizers, so history is trimmed a bit earlier than needed. The built-in engine has a `/tokenize` endpoint that could make this exact.
- **Memory search** loads all of a game's memory vectors each turn. That's fine up to several thousand memories; a per-game cache would help beyond that.
- **Editing and re-sending a fight-action message** keeps the action's effects while the text changes. It's rare and can be undone.
- **Raw uploads** (pictures, songs, rulebooks) have no request-size limit before reading. They're local-only, and the origin check above blocks other sites.
- The real llama.cpp engine, PyInstaller build, FastAPI routes and Hugging Face downloads were checked by reading and with stand-ins. FastAPI isn't installed in the test environments, so the first real run is still on your PC.
