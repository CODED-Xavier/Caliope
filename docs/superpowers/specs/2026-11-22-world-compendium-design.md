# World Compendium: rule sets and app-kept systems

Date: 2026-11-22 · Projects 3 + 4 of the current list (after the small fixes and companions)

## Why

Danilo plays role-play cards with game systems written into their text: Lumencia's EXP and sub-grades, and Black
Sheep's Credits, Frame Points, shop catalogs, bounty board, Top 8 ranking, romance ladder and d20 rolls. Today the
Aedo is asked to remember and calculate all of it, and a local 8B model drifts.

He wants two things:
- **General rules saved once in Calíope and ticked per card.** The first ones are his four Spectrums (Battle
  Difficulty, Durability, Speed, Strength).
- **The card's systems kept by the app.** Calíope should read a card's JSON and lorebook, find its systems, and run
  them for that card and any future card.

This is also groundwork for his own RPG later.

## Goals

1. **A World Compendium of rule sets,** each one ticked per card.
   - It grows out of today's 📚 Rules (rulebooks): a rule set is a rulebook with more parts. Existing rulebooks and
     card ticks keep working.
   - Each rule set has:
     - a **name and a short description**;
     - **core rules:** short text sent to the Aedo when the rules fit, for example the four Spectrum scales,
       about 400 words;
     - **when they apply:** *always*, *in fights and shows of power*, or *when the story uses these words* (an
       editable trigger list, like lorebook keywords);
     - **reference text** (optional): long explanations, imported files or a PDF. These are searched and sent only
       when relevant, as rulebooks work today;
     - **systems:** any number of app-kept blocks (goal 3).
   - **The rule (Danilo's):** a rule set comes into play when the Aedo is showing what someone can do (a fight, a
     duel, a show of power, speed or toughness, sizing up a rival), and stays out of plain conversation.
   - The Compendium has a **"New rule set" editor:** type or paste text, import .md, .txt or .pdf.
2. **Fights in role-play cards (narrated, no grid).**
   - **Start:** the Aedo picks the fight type (Spar, Battle or Lethal) and the Battle Difficulty (No, Low, Medium,
     High or Extreme), judging the gap between the fighters with the Strength, Speed and Durability scales. The
     tracker reports both.
   - **Shown when the fight starts:** "⚔ Duel: Lilia Valenheart · High difficulty · at least 5 exchanges".
   - **Pacing:** each difficulty has a minimum number of exchanges (No 1, Low 2, Medium 3, High 5, Extreme 8;
     editable). The app counts the player's turns and reminds the Aedo every turn, for example "exchange 2 of at
     least 5: she can be pushed back, not beaten".
   - **End:** the app computes EXP from the card's table (goal 3) and adds it to the sheet.
3. **System blocks** (fixed types; the app does the arithmetic and enforces the limits; each has a side-panel view):
   - **Currency:** a name (Credits, Crowns) and a starting amount. Purchases and rewards move it.
   - **Stat sheet:** named numbers or grades with ranges (Pilot Level 1–10, Integrity 0–30, Frame Points used/budget,
     Lumencia's sub-grade ladder D- … SSS+ with an EXP bar of 100).
   - **XP and levels:**
     - an XP-to-level table (Black Sheep: level 2 at 3 XP … level 10 at 27), or per-stat bars that roll over
       (Lumencia: 100 EXP raises a stat one sub-grade);
     - an award table by event (duel win +2, mission grade I–IV +1…+4);
     - for narrated fights: base award by fight type × difficulty multiplier × daily streak, + bonuses.
       Lumencia defaults: Spar 12, Battle 28, Lethal 50; No ×0.5, Low ×0.75, Medium ×1, High ×1.5, Extreme ×2;
       streak 1.0 / 1.25 / 1.5, reset each morning; +5 for a matching attribute of 7 or more.
   - **Catalog:** items or parts with slot, point cost, weight, effect, level gate, source and price, plus a
     budget (Frame Points by tier).
     - Buying checks the money, the level and the budget.
     - Installing updates the loadout and the net stats (Handling, Melee, Artillery, Endurance; speed from the
       number of Heavy parts).
   - **Mission board:**
     - grades with pay and level gates, and N jobs shown, refreshed on a weekday (Black Sheep: 3 jobs, Monday);
     - jobs are drafted by the Aedo from the card's rules (objective, complication, twist, choice, extra reward)
       and kept by the app: accepted, done or failed;
     - a mission log with merge and open threads.
   - **Ranking ladder:**
     - an ordered list (the Top 8), the player's place, pending challenges, protected-until days, the last 3 duels,
       and the next challenge due;
     - the challenge rules: Unranked challenges #8; a win swaps places; a loser is protected 2 days; a challenge is
       due every 3 days.
   - **Step tracker:**
     - steps per character (the romance ladder: Interest → Testing → Trust → Feelings → Reward);
     - limits: at most +1 step a day, no skipping, reviewed each night from the day's scenes.
   - **Roll formula:**
     - the formula, for example d20 + Pilot Level + a stat (Melee, Artillery or Handling) + matchup adjustments,
       against a target (the opponent's Threat);
     - damage by weight (Light 2, Medium 4, Heavy 6), minus armour by damage type, applied to a stat such as
       Integrity;
     - a natural 20 is an exceptional success, a natural 1 a complication.
     - In narrated duels each exchange shows a 🎲 button with this formula, filled from the sheet, and the app
       applies the result. "dice off" / "dice on" work as the card says.
   - **Calendar days** (already in Calíope): Day X/100 with weekdays and times of day. Systems use it (weekly
     refresh, protection days, nightly review).
4. **The card reader.**
   - Importing a card, or "🔍 Find systems" on an existing card, reads the card's text and lorebook with one AI pass
     and proposes rule sets and system blocks: their tables, numbers and starting values, quoted from the card.
   - A review screen shows each proposed block with its source entry: keep, edit or drop.
   - Kept blocks become a rule set named after the card (for example "Black Sheep systems"), ticked on that card,
     and usable by other cards.
   - The lorebook entries stay as the codex for the story. Their numbers now come from the app's state.
5. **Black Sheep fully playable.**
   - Imported, with its systems read and kept by the app: stat sheet, loadout, the four catalogs, the bounty board,
     the Top 8 with each pilot's Threat, the romance ladder, rolls, XP and levels, Credits, and Day X/100.
   - Its own rules are kept as written: never write {{user}}; 1% sync forever; English narration; the Codex line.
6. **Lumencia gets the Spectrums and the narrated-fight EXP calculator,** while keeping its current EXP rules. The
   calculator adds the difficulty multiplier.

## Non-goals

- A scripting language for rules (option 3, rejected): numbers live in editable tables inside the blocks.
- Grid combat for role-play cards: Black Sheep duels are narrated exchanges with roll buttons.
- Mechanics no block type covers: they stay as text for the Aedo, and a new block type can be added later.

## Anti-goals

- The Aedo calculating EXP, prices or budgets, or changing numbers the app keeps.
- Rule text crowding every reply: core rules only when they apply, reference text only when searched.
- Breaking existing cards and rulebooks: a card with no rule sets plays exactly as today.
- The reader inventing numbers the card doesn't state: unknowns are marked as gaps for the player to fill.

## Approaches considered

1. **Ready-made block types** (chosen): predictable, app-enforced, reusable, and reviewable after the reader runs.
2. Tracker keeps free-form values: cheap, but the arithmetic stays with the Aedo, so it drifts.
3. Rule sets with formulas or scripts: most flexible, but writing rules becomes programming and the reader can't
   reliably generate working scripts.

## How it works (decided)

- **Storage:** extend the `rulebooks` table rather than adding a new kind of thing, since cards already tick
  rulebooks. New fields:
  - `core_rules` (text);
  - `applies` (`always` | `fights` | `words`);
  - `trigger_words`;
  - `systems` (a JSON list of blocks: `{type, name, config}`).

  The existing house rules become the core rules with `applies = always`. Imported sections stay the reference text.
- **Game state:** `state.systems[block_id]` holds the live values: money, stats, loadout, board jobs, ranking,
  steps, the fight counter and the streak.
- **Prompt:** active core rules go in the stable part of the prompt when `always`, and in the volatile part when
  `fights` or `words` and triggered this turn. Each active block adds a short "current state" line, written by the
  app. The schema enum lists block events.
- **Tracker:** gets the new fields it may report:
  - `fight_start {opponent, type, difficulty}` and `fight_end {result}`;
  - `mission {accept | done | fail}`;
  - `buy {item}`;
  - `step {character, +1}`;
  - `challenge {…}`.

  The app validates every report against the blocks (money, level, budget, +1 a day) and applies it, or explains
  in the changes line why it didn't.
- **Panels:** one side-panel view per block type: Ranking, Board, Shop/Loadout, Romance, Fight.
- **Rolls:** reuse the check-button system with the rule set's roll formula.

## Left to the builder

- The panel layouts, and the exact reader prompt and schema.
- The order of the build phases. Suggested:
  1. rule sets and the editor;
  2. narrated fights with EXP;
  3. currency, sheet, XP and rolls;
  4. catalog;
  5. board;
  6. ladder and steps;
  7. the reader;
  8. the Black Sheep import and test.

## Builder check (done by Claude)

Calls I made:
- Rule sets extend rulebooks (same 📚 window, renamed **📚 Compendium**).
- The minimum exchanges per difficulty: No 1, Low 2, Medium 3, High 5, Extreme 8.
- Lumencia's base EXP per fight type is the middle of its current ranges.
- The default trigger words for the Spectrums are fight, duel, spar, attack, strike, blow, faster, stronger,
  overwhelm, power, speed and durability, in English and Portuguese.
- The four Spectrum files become one rule set, "Combat Spectrums": the short scales are the core rules (applies
  in fights and shows of power), and the full texts are reference.
- Black Sheep's 13 hidden codex entries (gaps in the source) stay gaps. The reader doesn't invent them.

- Mission jobs are shown with grade, pay and extra reward only. The complication and the twist are kept hidden
  and revealed during the mission, as the card says ("revealed mid-mission, never announced").

Questions only Danilo can answer, which change what gets built:
1. Should the Spectrum scales also apply in **adventure** (D&D grid) fights, to colour the narration only, or only
   in role-play cards?
