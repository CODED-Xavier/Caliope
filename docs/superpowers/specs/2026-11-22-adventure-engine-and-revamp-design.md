# Two engines, the 5e Adventure engine, and the new look

Date: 2026-11-22 · Comes before Portuguese play and the RP engine (World Compendium)

## Why

Danilo wants Calíope to play published-style adventures the way Foundry VTT and Roll20 do:
- the card is tied to a game system;
- a 5e library holds classes, races, backgrounds, feats, spells and items, and you drag what your character has
  onto the sheet, or let a builder fill it;
- the app does the arithmetic and runs features and level-ups.

He also wants the whole app easier to see and more interactive. And he wants **two separate engines**:
- **Adventure**: system-bound, rules fixed;
- **Role-play**: Lumencia and Black Sheep, with their own systems.

Each engine has its own panels and play screen, on one shared new look.

## Goals

1. **Cards tied to a system.**
   - Adventure cards have a **System** field: *D&D 5e (2014)* or *D&D 5e (2024)* (more later). The card list shows
     it: "Hollow Crown · D&D 5e".
   - The system's rules never change per card: checks, attacks, AC, proficiency and rests come from the engine, not
     from the card's text.
   - Role-play cards have no system; they use the RP engine (`2026-11-22-world-compendium-design.md`).
2. **The 5e library.**
   - **Built-in SRD pack:** the entries the 5e.tools files mark as SRD (`"srd": true`) — classes, subclasses,
     races, backgrounds, feats, spells, equipment. They're generated once from Danilo's files into
     `backend/app/seed/srd5e.json`, credited under CC-BY-4.0, and shipped with the app.
   - **His own files:** `backend/data/compendium/dnd5e/**.json` (never committed; `data/` is git-ignored) are read
     at start and add everything else.
   - **Edition filter by card system:** 2014 = PHB, XGE, TCE and the rest; 2024 = XPHB and the books marked for it.
   - **Search and sections:** Classes, Subclasses, Races, Backgrounds, Feats, Options (fighting styles,
     invocations, maneuvers), Spells, Items. Each entry shows its text with 5e.tools tags (`{@dice 1d10}`) turned
     into plain text.
3. **The character engine (5e).**
   - **The sheet stores references plus choices:** class and level (multiclass later), subclass, race and subrace,
     background, ability scores, chosen options and feats, spells known or prepared, inventory with
     equipped/attuned flags.
   - **Calíope works out:**
     - proficiency bonus, saves, skills, passive Perception;
     - AC from worn armour, shield and features (Defense +1, Unarmored Defense);
     - attacks from equipped weapons (ability, proficiency, damage, properties);
     - initiative, speed, HP by level;
     - spell slots, spell save DC and attack;
     - features with uses per short or long rest.
   - **Features with uses** have a **Use** button on the sheet and in fights (Second Wind heals 1d10 + level;
     Action Surge, Rage, Channel Divinity…). Rests refill them through the existing rest flow.
   - **Combat and checks read these numbers.** The fight uses the longsword's +5 / 1d8+3. Check buttons use the
     sheet's skill bonus.
   - **Legacy games:** existing games keep their free-form sheet. A "Convert to a 5e sheet" button runs the builder
     with what it can recognize.
4. **Drag and drop.**
   - The library opens as a column beside the sheet (the Sheet tab, or full screen on wide windows). Dragging an
     entry onto the sheet adds it; ＋ does the same (keyboard and touch).
   - Rules are checked on drop: a feat's prerequisite, a level 3 spell at level 1, a class feature above your level.
     A failed check is a clear message with "add anyway" for homebrew.
5. **The builder (like Roll20's Charactermancer).**
   - Steps: class → race → background → abilities (standard array, point buy, roll 4d6, manual) → class choices
     (skills, fighting style, cantrips, spells) → equipment (starting packages or gold) → review.
   - It's used by the new-game screen for 5e cards, replacing today's simple form, and by "Convert".
6. **Level-ups.**
   - XP or milestone (card setting). Reaching the XP threshold lights a **Level up** button.
   - The steps:
     - HP: take the average or roll;
     - the new features from the class table;
     - the real choices: subclass at its level, ASI or feat, new spells and options, Expertise…;
     - review.
   - It can be undone with ↶ like any change.
7. **The new look** (mockups: the "Calíope revamp mockups" canvas).
   - **Slim icon rail** instead of the wide sidebar: Menu, Games, Bestiary, Library, Muse, Settings.
   - **Top bar:** title, system and part; a scene chip; a day/time/weather chip; Recap, Undo, Restart.
   - **Strip under the top bar:**
     - Adventure: the party (player and companions) with HP bars, AC and ready features;
     - Role-play: the card's own tracker as chips (Lumencia: Tier, Body/Mana grades with EXP bars, Battles today;
       Black Sheep: Day 3/100, Rank, Credits, Integrity).
   - **Story:** **big portraits stay above the character's lines** (Danilo's choice). Roll requests and fight offers
     are coloured boxes with big buttons, showing the DC and your bonus before rolling.
   - **Side panel:** larger icon tabs. Each engine has its own set:
     - Adventure: Sheet, Combat, Map, People, Bag, Journal;
     - RP: Status, People, Journal, the card systems' panels.
   - **Both themes:** dark with violet accents, light with orange accents, same layout. Larger type and touch
     targets (44 px), clearer contrast.

## Non-goals

- Other systems (Pathfinder, Call of Cthulhu…) now: the System field is ready for them.
- Shipping non-SRD text: it only comes from the user's own files on their PC.
- Multiclassing in the first version (the sheet's data allows it later).
- Changing the RP engine's design beyond adding its tracker strip.

## Anti-goals

- The Aedo deciding numbers the engine knows (AC, attack, uses left).
- A sheet that silently accepts impossible combinations without saying so.
- Breaking existing games and cards: everything old keeps working, and conversion is optional.

## Approaches considered

1. **A real character engine (chosen):** references plus computed numbers; drag, builder and level-up share it.
2. Feature cards copied as text with guessed numbers: quicker, but the numbers drift and level-ups stay manual.
3. The builder only: no dragging a feat or item later, which Danilo asked for.

## How it works (decided)

- **Backend `app/dnd5e/` package:**
  - `library.py`: loads the SRD pack and the user's files; indexes them by type, name and source; filters by
    edition; renders text with tags stripped.
  - `character.py`: the sheet schema and the derived numbers.
  - `build.py`: the builder and level-up steps, as choice lists plus validation.
  - `srd_export.py`: a one-time script that writes the SRD pack from the user's files.
- **API:**
  - `/api/library/5e?type=&q=&edition=`
  - `/api/library/5e/entry/{type}/{source}/{name}`
  - `/api/conversations/{id}/character` (GET / PATCH add/remove/equip/choose)
  - `/api/conversations/{id}/character/levelup` (steps)
  - `/api/conversations/{id}/character/use` (a feature with uses)
- **State:** `state.character5e` (the references and choices). The free-form `state.player` stays and is filled
  from the derived numbers (name, HP, AC, stats), so everything that reads `player` keeps working.
- **Frontend:**
  - new `Library.jsx` (the column with search, sections and draggable entries);
  - `Sheet5e.jsx` (the engine's sheet);
  - `Builder.jsx` and `LevelUp.jsx` (the steps);
  - the revamp touches `App.jsx` (icon rail, top bar, strip), `styles.css` (tokens for both themes, sizes),
    `SidePanel.jsx` (tabs per engine) and `Chat.jsx` (roll and fight boxes; portraits stay big).

## Left to the builder

- The exact names of internal fields and helper functions, the library's paging, and how much 5e.tools tag syntax
  is turned into plain text beyond dice, damage, conditions and spells.
- The order of phases. Suggested:
  1. the revamp shell (rail, top bar, strip, themes);
  2. library loading and the SRD export;
  3. the character engine with the sheet;
  4. drag and drop;
  5. the builder;
  6. level-up;
  7. combat and check integration;
  8. converting Aster.

## Builder check (by Claude)

Calls I made:
- 2014 is the default edition for "D&D 5e".
- HP at level-up offers both the average and a roll.
- XP thresholds are the 5e table; milestone is a card setting.
- Ability scores in the builder: standard array, point buy, 4d6 or manual.
- A failed rule check offers "add anyway" (homebrew), marked on the sheet.
- The SRD pack is generated from the user's files instead of typed by hand, which keeps it exactly SRD text.

Nothing left that only Danilo can answer.
