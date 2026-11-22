# Companions and Solo Play Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cards can carry up to 3 companions that the Aedo voices and Calíope fights with automatically; solo games
scale adventure enemies to one hero; 0 HP means 5e death saving throws.

**Architecture:** A new `party.py` holds the companion rules: the sheet schema, the party state, enemy scaling,
building allies for combat, healing on rests, and the prompt section. Companions stay card NPCs with
`companion: true` and a `sheet`. The combat engine gains healer AI and death saves; the rest of the app calls
`party.py`.

**Tech Stack:** Python 3 / FastAPI / SQLite backend, React frontend; unittest; esbuild build check.

**Spec:** `docs/superpowers/specs/2026-11-22-companions-and-solo-design.md`

## Global Constraints

- At most 3 companions per card. Roles: `fighter | archer | healer | rogue`.
- Solo scaling: `count × party_size ÷ 4`, rounded, at least 1. Only adventure scene enemies are scaled.
- Death save: d20, 10+ succeeds, 9 or lower fails. Natural 20 = back at 1 HP. Natural 1 = 2 failures. 3 successes =
  stable, 3 failures = dead. A hit at 0 HP = 1 failure (a critical = 2).
- A long rest heals companions fully. A short rest heals half of their max HP, rounded up.
- UI text in English, with every new string in `pt-BR.json`. Keep README.md and BETA-TESTERS.md current.
- Cards without companions play exactly as today.

## Review Focus

1. A card edited after a game started (a companion added or renamed): the running game keeps its own party and
   doesn't crash. Pinned in Task 1 (normalize ignores unknown names).
2. A companion at 0 HP when a new fight starts: they don't join, and the party line says they're down. Pinned in
   Task 3.
3. The player dying while companions still stand: the fight goes on, and the healer heals the player first.
   Pinned in Task 4.
4. Solo with a scene of 1 enemy: it stays 1, never 0. Pinned in Task 2.
5. ↺ Restart of a companions game keeps the mode and restores the party at full HP. Pinned in Task 6.

---

### Task 1: Companion sheets on cards and the party state (`party.py`)

**Files:** Create `backend/app/party.py`. Modify `backend/app/scenarios.py` (npc normalize) and
`backend/app/state.py` (`_story_part`). Test: `backend/tests/test_party.py`.

**Interfaces — Produces:**
- `ROLES = ("fighter", "archer", "healer", "rogue")`
- `normalize_sheet(raw) -> dict`, giving
  `{class, role, hp, ac, attack_bonus, damage, range, speed, init_bonus, heal, heals}`.
  Defaults by role (5e level 1): fighter 12/16/+5/1d8+3/1/6; archer 10/14/+5/1d8+3/16/6;
  healer 10/16/+4/1d6+2/1/5 with heal 1d8+3 ×2; rogue 9/14/+5/1d6+3/1/6. All start at `init_bonus` +2.
- `companions(scenario: dict) -> list[dict]` (the card's npcs with `companion`, max 3).
- `start_party(state, scenario, mode: str) -> None`:
  - sets `state["party_mode"]` to `"solo"` or `"companions"`;
  - sets `state["party"] = {name: {"hp": max, "max_hp": max}}` (empty when solo).
- `party_size(state) -> int`: 1 + companions with HP above 0, or 1 when solo.

- [ ] Step 1: tests:
  - `test_sheet_defaults_by_role`: healer gets heal "1d8+3" and heals 2; an unknown role becomes fighter;
  - `test_card_keeps_companions`: `normalize_scenario` keeps `companion` and `sheet`, and caps at 3;
  - `test_start_party_solo_and_companions`;
  - `test_state_keeps_party`: `normalize_state` round-trips `party_mode` and `party`.
- [ ] Step 2: run, expect failures. Step 3: implement. Step 4: run, pass. Step 5: commit.

### Task 2: Solo scaling of adventure enemies

**Files:** Modify `backend/app/adventure.py` (`combat_enemies`). Test: `test_party.py`.

**Interfaces — Consumes:** `party.party_size(state)`. **Produces:** `scale_enemies(enemies, size) -> list` in
`party.py`; `combat_enemies(adv, state)` returns scaled counts and adds `"scaled_for": size` to each entry when
the count changed.

- [ ] Tests:
  - `test_scale`: 4 goblins at size 1 → 1; at size 4 → 4; 1 bugbear at size 1 → 1; 6 wolves at size 2 → 3.
  - `test_combat_enemies_uses_party`.
- [ ] Implement, run, commit.

### Task 3: Companions join fights as allies, and their HP is written back

**Files:** Modify `backend/app/party.py`, `backend/app/combat.py` (`start`, `_sync_player`), `backend/app/main.py`
(combat start: `allies = party.allies(state)` added to `body["allies"]`). Test: `test_party.py`.

**Interfaces — Produces:**
- `allies(state, scenario) -> list[dict]`: combatant dicts for living companions, with `current_hp`, `heal`,
  `heals` and `role`.
- In `combat.py`, `_combatant` keeps `role`, `heal` and `heals_left` for allies.
- `_sync_player` also writes ally HP back into `state["party"][name]["hp"]`.

- [ ] Tests:
  - `test_allies_skip_the_fallen`;
  - `test_ally_hp_goes_back_to_party` (start a fight with 1 companion, damage them, sync, check
    `state["party"]`).
- [ ] Implement, run, commit.

### Task 4: Healer AI and death saves

**Files:** Modify `backend/app/combat.py` (`_others_until_player`, `_attack`, `_finished`, `player_action`, new
`_death_save`). Test: `backend/tests/test_party.py`.

**Interfaces — Produces:**
- Player combatant fields: `dying: bool`, `stable: bool`, `dead: bool`, `death: {"ok": int, "fail": int}`.
- `_death_save(combat, me) -> str` writes a "💀 Death save: d20(n) → success (2/3)" line.
- `_finished` returns "you have fallen" only when nobody on the player's side is standing. When the player is
  dying or stable at that moment, the remaining saves are rolled with `_death_save` until stable or dead, and the
  end line says which.

- [ ] Tests (seeded dice):
  - `test_healer_heals_lowest_first`: a dying player beats a hurt fighter;
  - `test_heals_run_out`;
  - `test_drop_to_zero_means_dying`: the fight is still active when an ally stands;
  - `test_three_failures_dead` and `test_nat20_back_up`;
  - `test_hit_while_dying_is_a_failure`;
  - `test_alone_and_down_ends_the_fight_with_saves_rolled`.
- [ ] Implement:
  - at the start of the player's turn while dying, roll the save instead of letting them act;
  - `player_action` returns that save as the turn;
  - the healer acts in the ally branch before attacking when someone is below half HP or dying, and the
    healed player loses `dying` and returns at the healed HP.
- [ ] Run, commit.

### Task 5: Rests, the prompt section and the game start

**Files:** Modify `backend/app/resources.py` (`regenerate`: companions heal on `short_rest`/`long_rest`),
`backend/app/prompts.py` (a "Your companions" section in the stable part), `backend/app/conversations.py`
(`create(..., party_mode="")` calls `party.start_party`; companions are only made into NPC rows when mode is
`companions`), and `backend/app/main.py` (create body `party`). Test: `test_party.py`.

**Interfaces — Produces:** `party.prompt_section(state, npcs) -> str`. One line per companion: name, role, HP,
personality, speech style, relationship. Then the rule: *"They travel with the player. Voice them and let them speak
and act on their own initiative and react to the player, but never speak, think or decide for the player, and don't
let them crowd every reply. In fights, their actions come from the ⚔️ block only."*

- [ ] Tests:
  - `test_rests_heal_companions` (short: half of max rounded up; long: full);
  - `test_prompt_lists_companions`;
  - `test_solo_game_has_no_companion_rows`.
- [ ] Implement, run, commit.

### Task 6: Restart keeps the mode; drafting companions with the AI

**Files:** Modify `backend/app/conversations.py` (`restart` passes `party_mode`) and `backend/app/main.py`
(`POST /api/scenarios/{id}/companions/draft` → `{companions: [...]}` from one LLM call with a JSON schema of 3
companions using `normalize_sheet` fields plus name, personality, speech_style, appearance). Test: `test_party.py`.

- [ ] Test: `test_restart_keeps_party_mode` (party back at full HP). The draft endpoint goes through FakeLLM in a
  repository-level function `party.parse_draft(raw) -> list[dict]` (test: `test_parse_draft_caps_and_normalizes`).
- [ ] Implement, run, commit.

### Task 7: Frontend — the Companions window, the start choice, fight view

**Files:**
- Create `frontend/src/components/CompanionsEditor.jsx`.
- Modify:
  - `ScenarioModal.jsx`: a "👥 Companions" button opens the editor; companions are hidden from the normal
    characters list;
  - `SetupView.jsx`: "Play solo / Play with companions" when the card has companions; sends `party`;
  - `api.js`: `draftCompanions`;
  - `CombatTab.jsx`: allies show HP; the player shows "💀 dying · ✔✔✖" while dying;
  - `SidePanel.jsx`: the People card marks companions with a 👥 tag and shows their HP;
  - `pt-BR.json`, `styles.css`, README, BETA-TESTERS.
- [ ] Build with esbuild (no errors). Screenshot the editor and the start choice on the stub server. i18n
  missing-string check is clean for the touched files.
- [ ] Commit.

### Task 8: The Cragmaw card's companions, install and live check

- [ ] Write 3 companions into card 7 through the API on the PC:
  - Dorna Ironhand, dwarf cleric, healer: HP 10, AC 16, mace +4 1d6+2, heal 1d8+3 ×2; gruff, protective,
    drinks to the dead;
  - Faelar Quickbow, elf ranger, archer: HP 11, AC 14, longbow +5 1d8+3, range 16; quiet, wry, notices
    everything;
  - Pip Thistledown, halfling rogue: HP 9, AC 14, shortsword +5 1d6+3; cheerful, nosy, haggles over everything.
- [ ] Full test suite (sandbox and PC), install with hash checks, commit and tag v2.26.0, branch
  `feature/companions-solo`.
