# Calíope: notes for developers and AI helpers

Calíope is a local roleplay / tabletop RPG app. One FastAPI server (`backend/app/main.py`) serves the API and the
built React interface (`frontend/dist`). The AI is either LM Studio or the built-in llama.cpp engine (`runtime.py`).
Single user, localhost only, no login. The owner does not program: changes must keep `Play.bat` one-click.

## Names used in the interface
- **Calíope**: the app (files and the exe use `Caliope`, without the accent).
- **the Aedo**: the game master (the code still says GM / `gm_world`, `gm_cast`).
- **Cantos**: chapters of a story. **the Muse**: the writing helper.

## Layout
- `backend/app/`: `engine.py` runs a turn (prompt, stream, tracker, memories); `prompts.py` builds the prompt
  (stable system prefix first, volatile `[GM notes]` attached to the newest user message, so the model's cache is reused);
  `conversations.py` + `db.py` are the SQLite store (snapshots for undo are zlib-compressed in `messages.snapshot`);
  `services.py` wires everything. Game systems done by code, not the AI: `combat.py`, `worldtime.py` (calendar),
  `resources.py`, `shop.py`, `checks.py`, `statusbook.py` (INFO block), `signals.py` (skip the tracker on quiet turns).
- `backend/tests/`: `python -m unittest discover -s tests -t .` from `backend/`. `tests/test_api_smoke.py` imports `main.py`
  and calls endpoints straight through ASGI (no network); it runs wherever FastAPI is installed and is skipped elsewhere. A fake model is used; no GPU, network
  or LM Studio needed. `make_services()` in `tests/test_core.py` gives a fresh in-memory app.
- `frontend/src/`: React (no router, no state library). API calls only in `api.js`. Help texts for `?` tips in `helpTexts.js`.
- `backend/launcher.py` (Play.bat), `backend/desktop.py` + `build_exe.py` (Caliope.exe), `assets/` (icon).

## Rules that keep the app working
- Prefer code over the AI for anything countable (dice, money, HP, time, resources). The 8B model only narrates.
- Turns that change the state before the message (combat, trade, ability, rest, time skip) store a snapshot on the
  user message; undo, rewind and re-send restore it.
- Never send names or player text to online picture services; never send anything online without a setting the user turned on.
- Keep `local_only` (Host/Origin check) in `main.py`. Never `eval`/`exec` text from cards, Library files or the model
  (`dnd5e/levels._formula` shows a safe arithmetic reader). Uploads have size limits (`UPLOAD_LIMITS`).
- New settings: add to `DEFAULT_SETTINGS` in `config.py` (validate in `_coerce`), a help text, and a Settings row.
- Each feature: its own branch, tests, a README section, then a version tag (`v2.x.0`).
- Interface text is written in English in the components. Every new visible text (labels, buttons, tooltips,
  placeholders, help texts, backend error messages) also gets its Português (Brasil) line in
  `frontend/src/i18n/pt-BR.json` ("exact", or "patterns" with {0}, {1}… for names and numbers). The watcher in
  `i18n/index.js` swaps them on screen; story text (`.bubble`) and anything typed are never translated. Mark other
  user content with the `no-tr` class.
- `frontend/src/dialogs.jsx`: use `await ask.confirm/prompt/alert`, never the browser's `window.confirm/prompt/alert`.
