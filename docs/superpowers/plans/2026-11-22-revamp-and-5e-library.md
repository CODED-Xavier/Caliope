# New Look and 5e Library Implementation Plan (plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Calíope gets its new look (icon rail, top bar, engine strip, larger tabs, both themes) and a searchable D&D 5e
library: the built-in SRD plus the user's own 5e.tools files, browsable from a Library window.

**Architecture:**
- The revamp reshapes the existing React shell (`App.jsx`, `Sidebar.jsx`, `SidePanel.jsx`, `Chat.jsx`, `styles.css`)
  without changing the API.
- The library is a new backend package, `app/dnd5e/`, that loads SRD and user JSON into an in-memory index served by
  two endpoints, plus a `Library.jsx` view.
- Cards gain a `system` field. Plan 2 (character engine, drag and drop, builder, level-up) builds on this.

**Tech Stack:** FastAPI + SQLite, React (esbuild check), unittest; Playwright on the stub server for screenshots.

**Spec:** `docs/superpowers/specs/2026-11-22-adventure-engine-and-revamp-design.md`

## Global Constraints

- Systems: `"dnd5e-2014"` (default) and `"dnd5e-2024"`; role-play cards have no system.
- 2024 = source in {XPHB, XDMG, XMM} or `edition == "one"`; everything else is 2014.
- The SRD pack holds only entries with `"srd": true` (or `srd52` for 2024). It is credited: "Contains material from the
  System Reference Document 5.1/5.2 by Wizards of the Coast, CC-BY-4.0".
- The user's files live in `backend/data/compendium/dnd5e/` (git-ignored) and are never copied into the repo.
- Themes: dark accent `#a77bea` with `#f0a050`; light accent `#d9661a` with `#6d3cc2`. Same layout. Touch targets at
  least 44 px.
- Big portraits stay above the character's lines.
- Every new string goes into `pt-BR.json`. README and BETA-TESTERS stay current.

## Review Focus

1. A missing or broken user file (bad JSON, unexpected shape): the library loads the rest and reports the file, with
   no crash. Pinned in Task 2.
2. The same entry in SRD and user files (Second Wind PHB): it appears once, from the user's richer copy. Pinned in
   Task 2.
3. A narrow window (≤900 px) with the side panel open: the rail stays, the strip wraps, nothing overflows. Pinned in
   Task 5 (screenshot at 900 px).
4. Role-play cards: the strip shows tracker chips, never the party strip. Pinned in Task 5.
5. A card with no `system` (older adventure cards) behaves as `dnd5e-2014`. Pinned in Task 4.

---

### Task 1: 5e.tools text rendering

**Files:** Create `backend/app/dnd5e/__init__.py`, `backend/app/dnd5e/text.py`. Test: `backend/tests/test_dnd5e_library.py`.

**Interfaces — Produces:**
- `strip_tags(s: str) -> str`:
  - `{@dice 1d10}` → `1d10`; `{@spell fireball|PHB}` → `fireball`; `{@hit 5}` → `+5`; `{@dc 13}` → `DC 13`;
  - `{@atk mw}` → `Melee Weapon Attack:`; `{@h}` → `Hit:`;
  - any other `{@tag a|b|c}` → `c` when 3 parts, else `a`.
- `render(entries) -> str`: flattens strings, dicts `{type: entries|section|inset, name, entries}`, `list`
  (`items` → "• …"), `table` (rows joined by " | "), `item` (`name: entry`).

- [ ] Test `test_strip_tags` with the values above, and `test_render_nested` (a list inside entries with a named
  sub-entry).
- [ ] Run, expect failure. Implement. Run, pass. Commit.

### Task 2: Library loading and index

**Files:** Create `backend/app/dnd5e/library.py`. Test: `test_dnd5e_library.py`.

**Interfaces — Produces:**
- `TYPES = ("class", "subclass", "classFeature", "subclassFeature", "race", "subrace", "background", "feat", "optionalfeature", "spell", "baseitem", "item")`
- `edition_of(entry: dict) -> str`: returns `"2014"` or `"2024"`.
- `class Library`:
  - `__init__(self, folders: list[Path])`;
  - `load() -> dict`, returning `{"entries": n, "files": n, "errors": [str]}`;
  - `search(type: str, q: str = "", edition: str = "2014", limit: int = 60) -> list[dict]`, each item
    `{type, name, source, edition, srd, level?, class?, summary}`;
  - `get(type, source, name) -> dict | None` (raw plus `"text"`).
- Duplicates: the key is `(type, name.lower(), source)`; a later folder wins (user files after the SRD pack).
- `classFeature` and `subclassFeature` keep `className`, `level`, `subclassShortName`.

- [ ] Tests (temp folders with tiny JSON files):
  - `test_loads_types_and_editions`;
  - `test_search_by_name_and_edition`;
  - `test_bad_file_is_reported_not_fatal`;
  - `test_user_copy_wins_over_srd`.
- [ ] Implement, run, commit.

### Task 3: The SRD pack export and the built-in load

**Files:** Create `backend/app/dnd5e/srd_export.py` (a script: `python -m app.dnd5e.srd_export <folder>` writes
`backend/app/seed/srd5e.json`). Modify `backend/app/dnd5e/library.py` (built-in pack first). Test:
`test_dnd5e_library.py`.

**Interfaces — Produces:** `export(folder: Path, out: Path) -> dict` (counts per type). It keeps only `srd`/`srd52`
entries, drops `fluff`, `page` and images, and writes `{"_credit": "<CC-BY line>", "<type>": [...]}`.
`default_library(data_dir: Path) -> Library`, using folders `[seed/srd5e.json, data_dir/compendium/dnd5e]`.

- [ ] Test `test_export_keeps_only_srd` (a mixed temp file → only srd entries, credit present).
- [ ] Implement, run, commit.
- [ ] Run the export on the PC against the user's files, and copy `srd5e.json` into the repo seed. Check its size is
  under 5 MB and the counts are sane (about 300 spells, 12 classes).

### Task 4: Cards get a system; library endpoints

**Files:**
- Modify `backend/app/scenarios.py`: normalize `system`, valid `"dnd5e-2014" | "dnd5e-2024" | ""`. An adventure card
  missing it gets `"dnd5e-2014"`.
- Modify `backend/app/main.py`:
  - `GET /api/library/5e?type=&q=&edition=&limit=`;
  - `GET /api/library/5e/entry?type=&source=&name=`;
  - `GET /api/library/5e/status` (counts, errors, user folder path);
  - `POST /api/library/5e/reload`.

  The library loads lazily on first use, in a thread.
- Test: `test_dnd5e_library.py` (`test_card_system_normalized`).

- [ ] Test, implement, run the full suite, commit.

### Task 5: The new look — shell, themes, strip

**Files:**
- Modify `frontend/src/styles.css`: tokens for both themes per Global Constraints, a larger base size (15 px UI,
  17 px story), 44 px buttons in bars, and new classes `.rail`, `.topbar2`, `.chip`, `.engine-strip`, `.party-card`,
  `.tracker-chip`, `.panel-tabs` (a grid of icon tabs).
- Modify `frontend/src/components/Sidebar.jsx` into a **rail** (icons plus small labels): Menu, Games (opens a
  games drawer with the old list, rename/restart/delete), Bestiary, Library, Muse, Skills, Rules, Models, Settings,
  theme toggle.
- Modify `frontend/src/App.jsx`:
  - the top bar: title + "system · scene" subline; chips (📍 scene, 📅 date/time/weather); Recap, Undo, Restart;
    jukebox; Aa;
  - the **engine strip** under it:
    - adventure: party cards for the player (HP bar, AC) and companions (from `state.party`);
    - role-play: tracker chips parsed from `status_now` lines (`Label: value` segments).
- Modify `frontend/src/components/SidePanel.jsx`: the tab row becomes `.panel-tabs` (icon + label, 2 rows if
  needed); keep the scroll behaviour on narrow panels.
- Modify `frontend/src/components/Chat.jsx`: roll requests and fight offers become `.ask-box` with 44 px buttons
  showing the DC and your bonus. Portraits stay big above lines.
- Create `frontend/src/components/Library.jsx`: a modal with search, section chips and a result list. Each entry
  opens its text. A "Your files" line shows counts and the folder. Opened from the rail.
- [ ] esbuild build OK. Stub screenshots: play screen dark and light at 1400 px and 900 px, an RP card strip, the
  Library modal. i18n missing check clean.
- [ ] Commit.

### Task 6: Install, docs and live check

- [ ] README (new look, Library, system field) and BETA-TESTERS; version table line `2.27.0`.
- [ ] Full test suite in the sandbox and on the PC; install with hash checks; commit and tag `v2.27.0`, branch
  `feature/new-look-library`.
- [ ] If Calíope is open on the PC: library status and one search through the browser pane.
