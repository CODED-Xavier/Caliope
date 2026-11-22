# 5e Character Engine Implementation Plan (plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Adventure games get a real D&D 5e character: references to Library entries plus choices, with every number worked
  out by Calíope (AC, attacks, saves, skills, HP, features with uses, spell slots).
- The sheet is built by dragging from the Library, by the builder, and by level-ups.
- Fights and checks use these numbers.

**Architecture:**
- `app/dnd5e/character.py`: a pure engine. `derive(char, lib)` reads the character dict and the Library and returns
  the computed sheet.
- `app/dnd5e/build.py`: the choice lists and validation for adding entries, the builder steps and level-up.
- Endpoints on `main.py` store `state.character5e`. After every change they write the derived numbers into
  `state.player`, so combat, prompts and the status block keep working.
- `Sheet5e.jsx` shows the derived sheet with the Library column for drag and drop. `Builder.jsx` and `LevelUp.jsx`
  run the steps.

**Tech Stack:** FastAPI, unittest with a tiny fixture library, React + esbuild, Playwright on the stub server.

**Spec:** `docs/superpowers/specs/2026-11-22-adventure-engine-and-revamp-design.md` (goals 3–6)

## Global Constraints

- **Proficiency bonus by level:** +2 at 1–4, +3 at 5–8, +4 at 9–12, +5 at 13–16, +6 at 17–20.
- **XP thresholds (2014):** 0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000, 85000, 100000, 120000,
  140000, 165000, 195000, 225000, 265000, 305000, 355000.
- **AC:**
  - no armour: 10 + DEX;
  - light armour (LA): base + DEX;
  - medium (MA): base + DEX (at most 2);
  - heavy (HA): base;
  - shield (S): +2;
  - Barbarian Unarmored Defense: 10 + DEX + CON; Monk: 10 + DEX + WIS (both without armour, Monk also without a
    shield);
  - Fighting Style Defense: +1 while wearing armour.
- **Weapons:**
  - finesse (`F`) uses the better of STR and DEX; ranged (`type R`) uses DEX; the rest use STR;
  - proficient when the class has the weapon's category (`simple`/`martial`) or the weapon by name;
  - versatile (`V`) uses `dmg2` when no shield is held;
  - Archery: +2 to hit with ranged weapons; Dueling: +2 damage with a one-handed melee weapon and no other weapon.
- **HP:** level 1 = hit die maximum + CON mod. Each later level adds `rolls[i]`, or the average (faces ÷ 2 + 1),
  plus the CON mod, at least 1 per level.
- **Race ability bonuses:** from `ability` (a fixed dict). A PHB Human with no `ability` gets +1 to all six. A
  `choose` gets the player's picks.
- **Uses per rest** (2014 SRD, keyed by feature name):
  - Second Wind 1/short; Action Surge 1/short (2 from 17);
  - Rage 2/3/4/5/6 at 1/3/6/12/17, long;
  - Channel Divinity 1/short (2 from 6, 3 from 18); Bardic Inspiration = CHA mod (min 1), long, short from 5;
  - Ki = level, short (from 2); Wild Shape 2/short (from 2); Lay on Hands = 5 × level points, long;
  - Arcane Recovery 1/long; Sorcery Points = level, long (from 2); Divine Sense = 1 + CHA mod, long.
- **Spell slots:**
  - full casters use the 5e multiclass table rows 1–20;
  - half casters (`casterProgression "1/2"`) use row ceil(level ÷ 2) when level ≥ 2;
  - `"1/3"` uses row ceil(level ÷ 3) when level ≥ 3;
  - `"pact"` uses Warlock slots (1 at 1, 2 at 2–10, 3 at 11–16, 4 at 17+; slot level = min(5, ceil(level ÷ 2)))
    and refills on a short rest.
- Old games without `character5e` keep their free-form sheet.

## Review Focus

1. A character referencing a Library entry that is missing (a user file removed): the sheet still derives, the
   entry shows "missing from the library", and nothing crashes. Pinned in Task 1.
2. Two shields or two suits of armour equipped: only the best one counts, and the sheet says why. Pinned in Task 1.
3. A level-up past 20, or a choice sent twice: refused with a clear message. Pinned in Task 4.
4. Using a feature with no uses left: refused ("No uses left until a short rest"). Pinned in Task 3.
5. HP after a level-up while hurt: the current HP rises by the same amount as the max. Pinned in Task 4.

---

### Task 1: Abilities, proficiency, saves, skills, AC, HP, speed

**Files:** Create `backend/app/dnd5e/character.py`. Test: `backend/tests/test_dnd5e_character.py`, with a fixture
library from temp JSON holding Fighter, Barbarian, Human, Dwarf (Hill), Soldier, Longsword, Rapier, Longbow, Chain
Mail, Leather Armor, Shield, and the Defense/Archery/Dueling fighting styles.

**Interfaces — Produces:**
- `new_character(edition="2014") -> dict` with keys:
  - `edition, cls {name, source}, subclass {name, source}|None, level, race, subrace, background`;
  - `scores {str..cha}, picks {race_ability:{}, asi:[{ability:+n}], skills:[], expertise:[]}`;
  - `options [{type:"optionalfeature", name, source}], feats [{name, source}], spells [{name, source}]`;
  - `items [{type, name, source, qty, equipped}]`;
  - `hp {current, rolls:[]}, uses {feature: used}, xp, extras [{name, text, homebrew:true}]`.
- `derive(char, lib) -> dict` with keys:
  - `abilities {k: {score, mod}}, prof, saves {k: bonus}, skills {name: {bonus, proficient, expertise}}`;
  - `passive_perception, ac, ac_how, hp_max, hp, initiative, speed, hit_die`;
  - `attacks [], features [], slots {}, warnings []`.
- `SKILLS` = the 18 skills with their ability.

- [ ] Tests:
  - `test_fighter_aster`: STR 17, DEX 14, CON 16; Human +1 → STR 18 mod +4; chain mail + shield + Defense → AC 19;
    HP 10 + 4 = 14 at level 1; saves STR/CON proficient;
  - `test_medium_armor_dex_cap`;
  - `test_unarmored_defense_barbarian`;
  - `test_hp_with_rolls_and_average`;
  - `test_missing_entry_is_a_warning`;
  - `test_two_armours_best_counts`.
- [ ] Implement, run, commit.

### Task 2: Attacks, features with uses, spell slots

**Files:** Modify `character.py`. Test: `test_dnd5e_character.py`.

**Interfaces — Produces:**
- `attacks` items: `{name, bonus, damage, dtype, range, properties, proficient}`.
- `features` items: `{name, level, source, text, uses_max?, used?, per?: "short"|"long"}`. Class features up to the
  level come from the class's `classFeatures` refs; subclass features come from `subclassFeature` matching
  `className` and `subclassShortName` up to the level.
- `slots {1: n, ...}` and `pact {count, level}`.

- [ ] Tests:
  - `test_longsword_versatile_and_shield` (+6 1d8+4 with shield, 1d10+4 without);
  - `test_finesse_uses_dex`;
  - `test_archery_and_dueling`;
  - `test_second_wind_uses`;
  - `test_rage_by_level`;
  - `test_wizard_slots_level5` ({1: 4, 2: 3, 3: 2});
  - `test_paladin_half_caster_level1_has_no_slots`.
- [ ] Implement, run, commit.

### Task 3: Storing the character, editing it, using features, rests

**Files:** Create `backend/app/dnd5e/store.py`. Modify `backend/app/main.py`, `backend/app/resources.py` (rest refills
`character5e.uses` by `per`; pact slots on short rest). Test: `backend/tests/test_dnd5e_store.py`.

**Interfaces — Produces:**
- `apply_change(char, change: dict, lib) -> dict`. Change ops:
  - `add {type, name, source}` → routes to items, feats, options, spells, or class/race/background;
  - `remove {index|name}`; `equip {index, on}`; `set {field, value}` (scores, level, hp_current, xp);
  - `pick {kind, value}` (skills, expertise, race_ability, asi).

  It validates through `build.check_add` (Task 4) and raises `ValueError` with a player-facing message.
- `use_feature(char, name) -> tuple[dict, str]`; for Second Wind, the line includes the healing roll.
- `sync_player(state, derived) -> None`: writes `player.name`, `class`, `level`, `hp {current, max}`, `ac`,
  `stats`, `skills` (formatted).
- **Endpoints:**
  - `GET /api/conversations/{id}/character` returns `{character, sheet}`;
  - `PATCH /api/conversations/{id}/character` with body `{change}` returns `{character, sheet}`;
  - `POST /api/conversations/{id}/character/use` with body `{name}` streams a turn with the use line.

- [ ] Tests:
  - `test_add_item_and_equip`;
  - `test_use_second_wind_then_none_left`;
  - `test_short_rest_refills`;
  - `test_sync_player_numbers`.
- [ ] Implement, run, commit.

### Task 4: Checks on add, the builder, level-up

**Files:** Create `backend/app/dnd5e/build.py`. Test: `backend/tests/test_dnd5e_build.py`.

**Interfaces — Produces:**
- `check_add(char, entry, kind, lib) -> str`: an empty string if allowed, else the reason. It checks:
  - feat prerequisites: `proficiency armor`, `ability` minimums, `level`;
  - spell level ≤ the highest slot level;
  - a class feature's level ≤ the character's level.

  `homebrew=True` skips the checks and marks the entry.
- `builder_steps(char, lib) -> list[dict]`: each `{id, title, done, options?, count?}` for class, race, background,
  abilities (methods `standard` [15,14,13,12,10,8], `pointbuy` 27 points, `roll`, `manual`), skills (count and from
  the class), fighting style (if the progression has one at the level), equipment (starting items by name).
- `level_up_plan(char, lib) -> dict`: `{to_level, hp_average, hit_die, gains: [feature names], choices: [{id, kind, options, count}]}`.
  The choices are `subclass` at the class's first subclass-feature level, `asi_or_feat` at a feature named "Ability
  Score Improvement", and `optionalfeature` when the progression rises.
- `apply_level_up(char, answers: dict, lib) -> dict`. HP: `"average"` or `{"roll": n}`. It raises the current HP by
  the max increase. It refuses level 21 and missing choices.

- [ ] Tests:
  - `test_heavy_armor_master_needs_heavy_armor`;
  - `test_third_level_spell_refused_at_level1`;
  - `test_builder_steps_fighter`;
  - `test_level3_needs_subclass`;
  - `test_level_up_raises_current_hp`;
  - `test_no_level_21`.
- [ ] Implement, run, commit.

### Task 5: Fights and checks read the sheet

**Files:** Modify `backend/app/combat.py` (`player_defaults`) and `backend/app/checks.py` (`bonus_for`). Test:
`test_dnd5e_store.py`.

**Interfaces — Consumes:** `state["character5e_sheet"]`, the cached derived sheet written by `sync_player`.

- `player_defaults` uses the first equipped melee attack's bonus and damage and the sheet's AC.
- `bonus_for` uses `skills[name].bonus` and `saves[k]` when the cache exists.

- [ ] Tests:
  - `test_combat_uses_longsword`;
  - `test_check_uses_skill_bonus`.
- [ ] Implement, run the full suite, commit.

### Task 6: The 5e sheet, drag and drop, builder and level-up screens

**Files:**
- Create `frontend/src/components/Sheet5e.jsx`:
  - the header (name, race, class level, background, XP with a Level up button);
  - the six ability tiles, then AC (with its breakdown), HP, proficiency and speed;
  - features with Use buttons and uses pips, attacks, spell slots, items (equip toggles);
  - a drop zone, plus the Library column (reusing `Library.jsx` in a compact "pick" mode with draggable rows and
    ＋ buttons).
- Create `frontend/src/components/Builder.jsx` and `frontend/src/components/LevelUp.jsx`: steps with big option
  cards.
- Modify:
  - `SidePanel.jsx`: an adventure game with `character5e` shows Sheet5e in the Sheet tab; others keep today's sheet,
    plus a "Convert to a 5e sheet" button;
  - `SetupView.jsx`: 5e cards offer "Build with the 5e builder";
  - `api.js`, `pt-BR.json`, `styles.css`, README, BETA-TESTERS.
- [ ] Build OK. Stub screenshots of the sheet, a drop, the builder step and level-up. i18n clean. Commit.

### Task 7: Convert Aster, install, live check

- [ ] Convert endpoint: `POST /api/conversations/{id}/character/convert` builds `character5e` from `state.player`.
  It matches the class, race and background by name in the Library, copies stats and HP, and turns inventory names
  into item refs where found.
- [ ] Full suite (sandbox and PC); install with hash checks; tag `v2.28.0`, branch `feature/character-engine`.
- [ ] With Calíope closed (check first), back up the save file; convert Aster in the newest Cragmaw game; report his
  derived sheet.
