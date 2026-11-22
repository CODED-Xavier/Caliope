# Companions and solo play: design

Date: 2026-11-22 · For Calíope v2.26

## Why

Published adventures (Lost Mine of Phandelver) are written for 4–5 heroes. Played alone, the first ambush
(4 goblins) beats a level 1 fighter in one round, and dropping to 0 HP ends the fight at once. Danilo wants
two ways to play an adventure card:

- **Play solo:** the fights are scaled to one hero, and 0 HP means 5e death saving throws.
- **Play with companions:** up to 3 fixed companions who aren't part of the published story. They come from
  the card, each with a fight sheet, a personality and a look. The Aedo plays them in the story, Calíope plays
  them in fights, and they have relationship scores with the player like any character.

## Goals

1. A **Play solo / Play with companions** choice on the start screen of cards that have companions. Cards
   without companions are always solo, and the choice is hidden.
2. A **Companions** window in the card editor: up to 3 companions, each with
   - who they are: name, class, role, personality, speech style, looks;
   - a fight sheet: HP, AC, attack bonus, damage, range, speed, initiative bonus, and for healers a healing
     roll and how many heals they get per fight.

   **✨ Write companions** has the AI draft them to fit the card; you can edit everything.
3. **The story:** companions travel with the player. The Aedo voices them, lets them speak and act on their own
   initiative and react to the player, and never decides for the player. Their relationship with the player
   uses the existing relationship system, with the same scale, events and log.
4. **Fights:** companions join every fight automatically as allies (the combat engine already has allies). On
   their turn Calíope plays them:
   - a healer heals the most hurt member of the party (below half HP) while heals remain;
   - otherwise each walks to the nearest enemy and attacks, or shoots if their range allows.

   All dice are rolled by the app. The Aedo narrates them in their own voice.
5. **Companion HP lasts between fights,** like the player's. Rests restore it: a long rest fully; a short rest
   gives back half, rounded up.
6. **Solo scaling:** the adventure's scene enemies are multiplied by party size ÷ 4, rounded, with at least 1
   kept. Alone, 4 goblins become 1. With 3 companions all 4 stay. Fights built by hand in the Combat tab keep
   the numbers you chose. The Combat tab shows "scaled for a party of N".
7. **Death saving throws** (both modes). At 0 HP the player is *dying* and drops prone:
   - on each of the player's turns the app rolls a death save: 10+ is a success, 9 or lower a failure,
     a natural 20 brings the player back at 1 HP, a natural 1 counts as two failures;
   - 3 successes and the player is *stable*; 3 failures and the player *dies*;
   - a hit on a dying player is a failure, and a critical hit is two;
   - a companion healer heals a dying player first, which brings them back up.

   The fight is lost only when nobody on the player's side is standing. If the player is still only dying or
   stable at that point, the app rolls the remaining saves to the end:
   - stable: the player wakes later at 1 HP (left for dead or captured, as the Aedo tells it);
   - dead: the Aedo narrates the death, and ↺ Restart is offered.
8. **The Cragmaw test card gets 3 ready companions** (dwarf cleric, elf ranger, halfling rogue) written by Claude,
   so the feature can be tested right away.

## Non-goals

- Commanding companions by hand (Danilo chose automatic play).
- Companion level-ups, inventories and spells beyond one attack and one heal.
- Companions for roleplay (non-adventure) cards. The window is shown for every card, but fight scaling and
  death saves only matter where there is combat.

## Anti-goals (a failure even if it works)

- Companions taking over the story: speaking for the player, deciding for them, or crowding every reply.
- The Aedo inventing companion dice or damage in a fight (same rule as the player: the ⚔️ block is the truth).
- Fights becoming slow: still one Aedo reply per round.

## Approaches considered

1. **Companions are card characters (NPCs) marked as companions, with a fight sheet.** Chosen: they reuse
   relationships, looks, portraits, the People tab, the Aedo's notes and the character prompt.
2. A separate "party" block apart from characters. Rejected: it would duplicate relationships and looks, which
   could drift apart.
3. Reusable companions saved like personas and brought into any card. Rejected: Danilo wants them on the card,
   made in the card editor.

## How it works (decided)

- **On the card:** each companion is an `npcs` entry with `companion: true` and a `sheet`:

  ```
  {class, role: fighter|archer|healer|rogue, hp, ac, attack_bonus, damage, range, speed, init_bonus,
   heal: "1d8+3", heals: 2}
  ```

  `normalize_scenario` keeps both fields and caps companions at 3. They don't show in the normal Characters
  list; they show in the Companions window.
- **In a game:**
  - the start screen sends `party: "solo" | "companions"`, saved in the game state as `state.party_mode`;
  - with companions, the game's NPC rows are created as usual (met, active, in the prompt) and
    `state.party` holds `{name: {hp, max_hp}}`;
  - with solo, companions are left out of the game entirely, with no NPC rows.
- **Combat start:**
  - living companions (HP above 0) are added as allies from their sheet, with their current HP;
  - their HP goes back to `state.party` after every action, the same way the player's HP is written back now;
  - healer AI: in the ally branch of the turn loop, before attacking, if a healer has heals left and an ally
    or the player is below half HP (or dying), it heals them instead (`heals` is counted per fight).
- **Scaling:** `adventure.combat_enemies` gets the party size (1 + living companions in this game) and scales
  the counts. The fight offer and the Combat tab's suggestion both use it.
- **Death saves:**
  - the player combatant gets `dying`, `stable` and `death: {ok, fail}`;
  - the turn loop rolls the save at the start of the player's turn;
  - the engine's "you have fallen" check becomes "nobody on the player's side is standing".
- **Prompt:** a "Your companions" section lists each one with role, personality, speech style, HP and their
  relationship with the player, plus the rule in anti-goal 1. The existing combat rules already cover allies.
- **✨ Write companions:** one AI call with the card's setting, returning 3 companions in the schema above
  (5e numbers for a level 1 party).

## Left to the builder

- The exact layout of the Companions window: a modal from the card editor, or one card per companion with
  its sheet fields.
- The word choices in messages and narration hints, in English with pt-BR translations.
- The default numbers for each role (a level 1 cleric, ranger, rogue, fighter from the 5e basic rules).

## Builder check: calls I made (Claude)

- A short rest restores half of a companion's HP. The basic rules use hit dice; this is simpler.
- A healer heals anyone below half HP or dying; healing goes to the dying player first.
- Solo death is possible (3 failed saves). After a lost fight, a stable player wakes at 1 HP.
- Companions only exist in games started with **Play with companions**. Changing the mode needs a new game
  or a ↺ Restart.
- ↺ Restart keeps the game's mode.
