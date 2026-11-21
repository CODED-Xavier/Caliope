"""Combat tracked by code: initiative, attacks, damage, HP, conditions and positions on a grid.

The AI never decides a hit or a number. The app rolls, applies the result and sends the GM a line
starting with ⚔️ that says exactly what happened; the GM only narrates it.

Two presets:
    d20     D&D 5e style. Initiative d20 + DEX. Attack d20 + bonus against AC (natural 20 always hits and
            doubles the damage dice, natural 1 always misses). Damage dice, HP.
    pool    Vampire: the Masquerade 5e style. Roll a pool of d10s: each 6+ is a success, every pair of 10s
            adds 2 more. An attack is contested by the defender's pool; damage = margin + weapon bonus.
            Health is counted in boxes (HP).
"""
from __future__ import annotations

import random
import re
import uuid

from .dice import DiceError, DiceRoller
from .maps import blocked, clean_tiles, distance, has_cover, open_cells, path_step
from .util import as_int, clamp, truncate

SYSTEMS = ("d20", "pool")
SIDES = ("player", "ally", "enemy")
MAX_COMBATANTS = 16
GRID_MAX = 80  # an adventure's map picture can hold a big grid
CONDITIONS = ("prone", "grappled", "restrained", "poisoned", "stunned", "blinded", "frightened", "invisible", "dodging")


def _picture_geometry(battle_map: dict | None) -> dict:
    """An adventure map lined up with its own squares (geom) and the fog over the places not visited yet."""
    out: dict = {}
    g = (battle_map or {}).get("geom")
    if isinstance(g, dict):
        try:
            geom = {k: float(g[k]) for k in ("size", "ox", "oy", "nat_w", "nat_h")}
            if geom["size"] > 0 and geom["nat_w"] > 0 and geom["nat_h"] > 0:
                out["geom"] = geom
        except (KeyError, TypeError, ValueError):
            pass
    fog = (battle_map or {}).get("fog")
    if isinstance(fog, list):
        clean = []
        for f in fog[:100]:
            try:
                clean.append({"x": float(f["x"]), "y": float(f["y"]), "r": max(0.0, min(40.0, float(f["r"])))})
            except (KeyError, TypeError, ValueError):
                continue
        if clean:
            out["fog"] = clean
    return out


class CombatError(ValueError):
    pass


def ability_mod(score) -> int:
    return (as_int(score, 10) - 10) // 2


def _dice_ok(expr: str, default: str) -> str:
    expr = re.sub(r"\s+", "", str(expr or "")).lower()
    try:
        DiceRoller(random.Random(0)).roll(expr)
        return expr
    except DiceError:
        return default


def player_defaults(state: dict, system: str) -> dict:
    """The player's numbers for a fight, from the sheet."""
    p = state["player"]
    stats = p.get("stats") or {}
    if system == "pool":
        strength, dexterity = as_int(stats.get("Strength", stats.get("STR", 2)), 2), as_int(stats.get("Dexterity", stats.get("DEX", 2)), 2)
        # sheets with D&D scores: turn 10 into a 2-dot attribute
        dots = lambda v: v if v <= 5 else max(1, min(5, (v - 4) // 3))  # noqa: E731
        return {"pool": dots(max(strength, dexterity)) + 2, "defense": dots(dexterity) + 2, "damage": "1", "hp": max(3, as_int(p["hp"]["max"], 7))}
    mod = max(ability_mod(stats.get("STR", 10)), ability_mod(stats.get("DEX", 10)))
    prof = 2 + max(0, as_int(p.get("level", 1), 1) - 1) // 4
    return {"attack_bonus": mod + prof, "damage": f"1d8{mod:+d}" if mod else "1d8", "ac": as_int(p.get("ac", 10), 10),
            "init_bonus": ability_mod(stats.get("DEX", 10)), "hp": as_int(p["hp"]["max"], 10)}


def _combatant(raw: dict, side: str, system: str, index: int) -> dict:
    name = truncate(str(raw.get("name") or ("Enemy" if side == "enemy" else "Ally")).strip(), 40)
    hp_max = max(1, min(999, as_int(raw.get("hp", raw.get("max_hp", 7)), 7)))
    c = {
        "id": raw.get("id") or uuid.uuid4().hex[:8],
        "name": name,
        "side": side,
        "hp": hp_max if raw.get("current_hp") is None else int(clamp(as_int(raw["current_hp"], hp_max), 0, hp_max)),
        "max_hp": hp_max,
        "conditions": [x for x in raw.get("conditions", []) if x in CONDITIONS] if isinstance(raw.get("conditions"), list) else [],
        "x": as_int(raw.get("x"), -1),
        "y": as_int(raw.get("y"), -1),
        "init": 0,
        "notes": truncate(str(raw.get("notes") or ""), 120),
        "range": max(1, min(30, as_int(raw.get("range", 1), 1))),   # squares: 1 = melee, more = ranged
        "speed": max(1, min(12, as_int(raw.get("speed", 6), 6))),   # squares per turn (6 = 30 ft)
    }
    spell = raw.get("spell") if isinstance(raw.get("spell"), dict) else None
    if spell and str(spell.get("name", "")).strip():
        mp_max = max(1, min(999, as_int(raw.get("mp", raw.get("mp_max", 10)), 10)))
        c["mp_name"] = truncate(str(raw.get("mp_name") or "Mana").strip(), 16) or "Mana"
        c["mp_max"] = mp_max
        c["mp"] = mp_max if raw.get("mp_current") is None else int(clamp(as_int(raw["mp_current"], mp_max), 0, mp_max))
        c["spell"] = {"name": truncate(str(spell["name"]).strip(), 30), "cost": max(1, min(999, as_int(spell.get("cost", 3), 3))),
                      "damage": _dice_ok(spell.get("damage"), "2d6") if system != "pool" else str(max(0, min(10, as_int(spell.get("damage", 2), 2)))),
                      "range": max(1, min(30, as_int(spell.get("range", 12), 12)))}
    if system == "pool":
        c["pool"] = max(1, min(20, as_int(raw.get("pool", 4), 4)))
        c["defense"] = max(1, min(20, as_int(raw.get("defense", c["pool"]), c["pool"])))
        c["damage"] = str(max(0, min(10, as_int(raw.get("damage", 1), 1))))
    else:
        c["ac"] = max(1, min(40, as_int(raw.get("ac", 12), 12)))
        c["attack_bonus"] = max(-5, min(20, as_int(raw.get("attack_bonus", 3), 3)))
        c["damage"] = _dice_ok(raw.get("damage"), "1d6+1")
        c["init_bonus"] = max(-5, min(15, as_int(raw.get("init_bonus", 1), 1)))
    return c


class CombatEngine:
    def __init__(self, dice: DiceRoller | None = None, rng: random.Random | None = None):
        self.dice = dice or DiceRoller()
        self.rng = rng or random.Random()

    # ------------------------------------------------------------------ dice for pools
    def roll_pool(self, n: int) -> dict:
        rolls = [self.rng.randint(1, 10) for _ in range(max(0, n))]
        tens = rolls.count(10)
        successes = sum(1 for r in rolls if r >= 6) + (tens // 2) * 2
        return {"rolls": rolls, "successes": successes, "critical": tens >= 2}

    # ------------------------------------------------------------------ start / end
    def start(self, state: dict, system: str, enemies: list[dict], allies: list[dict] | None = None,
              player: dict | None = None, grid: dict | None = None, battle_map: dict | None = None,
              near: list | None = None) -> tuple[dict, str]:
        system = system if system in SYSTEMS else "d20"
        if not enemies:
            raise CombatError("Add at least one enemy.")
        defaults = player_defaults(state, system)
        me = {**defaults, **{k: v for k, v in (player or {}).items() if v not in (None, "")}}
        p = state["player"]
        me.update(name=p.get("name") or "You", current_hp=as_int(p["hp"]["current"], defaults["hp"]), hp=as_int(p["hp"]["max"], defaults["hp"]))
        people = [_combatant(me, "player", system, 0)]
        for side, group in (("ally", allies or []), ("enemy", enemies)):
            for raw in group:
                count = max(1, min(8, as_int(raw.get("count", 1), 1)))
                for i in range(count):
                    item = dict(raw)
                    if count > 1:
                        item["name"] = f"{raw.get('name') or 'Enemy'} {i + 1}"
                    people.append(_combatant(item, side, system, len(people)))
        if len(people) > MAX_COMBATANTS:
            raise CombatError(f"At most {MAX_COMBATANTS} combatants.")

        tiles: list[str] = []
        if battle_map and battle_map.get("tiles"):
            tiles = clean_tiles(battle_map["tiles"])
            w, h = len(tiles[0]), len(tiles)
        else:
            w = max(6, min(GRID_MAX, as_int((grid or {}).get("w", 12), 12)))
            h = max(4, min(GRID_MAX, as_int((grid or {}).get("h", 8), 8)))
        anchor = None
        if near and len(near) == 2:
            anchor = (max(0, min(w - 1, as_int(near[0], 0))), max(0, min(h - 1, as_int(near[1], 0))))
        self._place(people, w, h, tiles, anchor)
        log = []
        for c in people:
            if system == "pool":
                c["init"] = c.get("defense", 2) + self.rng.random()  # no initiative roll in V5: quicker side first
            else:
                r = self.dice.roll(f"1d20{c['init_bonus']:+d}" if c["init_bonus"] else "1d20")
                c["init"] = r.total + self.rng.random() / 10
                log.append(f"{c['name']} initiative {r.total}")
        people.sort(key=lambda c: -c["init"])
        combat = {"active": True, "system": system, "round": 1, "turn": 0, "order": [c["id"] for c in people],
                  "combatants": people, "grid": {"w": w, "h": h, "tiles": tiles,
                                                 "background": str((battle_map or {}).get("background") or "")[:600],
                                                 "name": truncate(str((battle_map or {}).get("name") or ""), 60),
                                                 **_picture_geometry(battle_map)},
                  "log": log[-30:]}
        state["combat"] = combat
        order = ", ".join(c["name"] for c in people)
        foes = ", ".join(f"{c['name']} ({c['hp']} HP)" for c in people if c["side"] == "enemy")
        line = f"⚔️ Combat starts! Turn order: {order}. Enemies: {foes}."
        return state, line

    @staticmethod
    def _place(people: list[dict], w: int, h: int, tiles: list[str] | None = None, anchor: tuple | None = None) -> None:
        """Your side near the left edge, enemies near the right, only on squares everyone can reach. With an anchor (the
        scene's spot on an adventure map), enemies gather around it and your side a few squares away."""
        cells = open_cells(tiles) if tiles else [(x, y) for x in range(w) for y in range(h)]
        taken = {(c["x"], c["y"]) for c in people if (c["x"], c["y"]) in set(cells)}
        mid = h / 2
        if anchor:
            ax, ay = anchor
            mx = ax - 4 if ax >= 4 else ax + 4
            right = sorted(cells, key=lambda p: (abs(p[0] - ax) + abs(p[1] - ay), p))
            left = sorted(cells, key=lambda p: (abs(p[0] - mx) + abs(p[1] - ay), p))
        else:
            left = sorted(cells, key=lambda p: (p[0], abs(p[1] - mid)))
            right = sorted(cells, key=lambda p: (-p[0], abs(p[1] - mid)))
        for c in people:
            if (c["x"], c["y"]) in taken and 0 <= c["x"] < w:
                continue
            pool = right if c["side"] == "enemy" else left
            spot = next((p for p in pool if p not in taken), None)
            if spot:
                c["x"], c["y"] = spot
                taken.add(spot)

    def end(self, state: dict, reason: str = "") -> tuple[dict, str]:
        combat = state.get("combat") or {}
        if not combat.get("active"):
            raise CombatError("There is no fight going on.")
        foes = [c for c in combat["combatants"] if c["side"] == "enemy"]
        down = [c["name"] for c in foes if c["hp"] <= 0]
        combat["active"] = False
        line = "⚔️ The fight is over" + (f": {reason}" if reason else ".") + (f" Defeated: {', '.join(down)}." if down else "")
        return state, line

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _get(combat: dict, cid: str) -> dict:
        for c in combat["combatants"]:
            if c["id"] == cid:
                return c
        raise CombatError("That combatant is not in this fight.")

    @staticmethod
    def current(combat: dict) -> dict:
        cid = combat["order"][combat["turn"] % len(combat["order"])]
        return next(c for c in combat["combatants"] if c["id"] == cid)

    def _sync_player(self, state: dict) -> None:
        me = next(c for c in state["combat"]["combatants"] if c["side"] == "player")
        state["player"]["hp"]["current"] = int(clamp(me["hp"], 0, state["player"]["hp"]["max"]))

    def _advance(self, combat: dict) -> None:
        """Next living combatant; a new round starts after the last one."""
        n = len(combat["order"])
        for _ in range(n):
            combat["turn"] += 1
            if combat["turn"] >= n:
                combat["turn"] = 0
                combat["round"] += 1
            cur = self.current(combat)
            if "dodging" in cur["conditions"]:  # a Dodge lasts until the dodger's own next turn
                cur["conditions"].remove("dodging")
            if cur["hp"] > 0:
                return

    def _attack(self, combat: dict, att: dict, target: dict, advantage: str = "", head: str = "") -> str:
        """One attack, written as a block:  header / 🎲 roll / 💥 damage."""
        tiles = combat["grid"].get("tiles") or []
        cover = has_cover(tiles, att["x"], att["y"], target["x"], target["y"])
        head = head or f"**{att['name']} attacks {target['name']}**"
        if combat["system"] == "pool":
            a = self.roll_pool(att["pool"] - (2 if "prone" in att["conditions"] else 0))
            d = self.roll_pool(target["defense"] + (2 if "dodging" in target["conditions"] else 0) + (1 if cover else 0))
            margin = a["successes"] - d["successes"]
            extra = " (cover: +1 defense die)" if cover else ""
            roll = f"🎲 {a['successes']} successes {a['rolls']} vs {d['successes']} {d['rolls']}{extra}"
            if margin <= 0:
                return f"{head}\n{roll} → **MISS**"
            dmg = margin + as_int(att["damage"], 0)
            target["hp"] = max(0, target["hp"] - dmg)
            crit = " (CRITICAL)" if a["critical"] else ""
            return (f"{head}\n{roll} → **HIT**{crit}\n💥 {dmg} damage → {target['name']} {target['hp']}/{target['max_hp']} HP"
                    + self._down(target))

        mode = advantage
        if "dodging" in target["conditions"] or "invisible" in target["conditions"]:
            mode = "disadvantage" if mode != "advantage" else ""
        if any(x in target["conditions"] for x in ("prone", "restrained", "stunned", "blinded")) and mode != "disadvantage":
            mode = "advantage"
        if any(x in att["conditions"] for x in ("poisoned", "frightened", "blinded", "restrained", "prone")):
            mode = "disadvantage" if mode != "advantage" else ""
        ac = target["ac"] + (2 if cover else 0)
        expr = "1d20" + (f"{att['attack_bonus']:+d}" if att["attack_bonus"] else "") + (f" {mode}" if mode else "")
        r = self.dice.roll(expr)
        hit = r.natural != 1 and (r.natural == 20 or r.total >= ac)
        tag = " (advantage)" if r.mode == "advantage" else " (disadvantage)" if r.mode == "disadvantage" else ""
        roll = (f"🎲 d20({r.natural}) {att['attack_bonus']:+d} = {r.total} vs AC {ac}"
                + (" (cover +2)" if cover else "") + tag)
        if not hit:
            return f"{head}\n{roll} → **{'natural 1, ' if r.natural == 1 else ''}MISS**"
        dmg_expr = att["damage"]
        if r.natural == 20:  # critical: double the dice
            dmg_expr = re.sub(r"(\d*)d(\d+)", lambda m: f"{2 * int(m.group(1) or 1)}d{m.group(2)}", dmg_expr)
        d = self.dice.roll(dmg_expr)
        dmg = max(1, d.total)
        target["hp"] = max(0, target["hp"] - dmg)
        crit = "CRITICAL HIT" if r.natural == 20 else "HIT"
        return (f"{head}\n{roll} → **{crit}**\n💥 {dmg} damage ({dmg_expr}) → {target['name']} {target['hp']}/{target['max_hp']} HP"
                + self._down(target))

    @staticmethod
    def _down(c: dict) -> str:
        if c["hp"] > 0:
            return ""
        return f" · **{c['name']} falls unconscious!**" if c["side"] == "player" else f" · **{c['name']} is defeated!**"

    def _finished(self, combat: dict) -> str:
        if all(c["hp"] <= 0 for c in combat["combatants"] if c["side"] == "enemy"):
            return "all enemies are down"
        if all(c["hp"] <= 0 for c in combat["combatants"] if c["side"] == "player"):
            return "you have fallen"
        return ""

    # ------------------------------------------------------------------ actions
    def player_action(self, state: dict, action: str, target_id: str = "", advantage: str = "", ability_id: str = "") -> tuple[dict, str]:
        """The player's action, then every other combatant until it is the player's turn again (one GM reply per round)."""
        combat = state.get("combat") or {}
        if not combat.get("active"):
            raise CombatError("There is no fight going on.")
        me = next(c for c in combat["combatants"] if c["side"] == "player")
        round_no = combat["round"]
        lines: list[str] = []
        # Anyone before the player in the order acts first (start of the fight, or after a free text turn).
        lines += self._others_until_player(combat)
        if me["hp"] <= 0:
            raise CombatError("You are unconscious.")
        if action == "attack":
            target = self._get(combat, target_id)
            if target["hp"] <= 0:
                raise CombatError(f"{target['name']} is already down.")
            lines.append(self._attack(combat, me, target, advantage if advantage in ("advantage", "disadvantage") else ""))
        elif action == "dodge":
            if "dodging" not in me["conditions"]:
                me["conditions"].append("dodging")
            lines.append(f"**{me['name']} dodges**\n🛡 Attacks against {me['name']} have disadvantage until their next turn.")
        elif action == "other":
            lines.append(f"**{me['name']} acts**\n✋ See the player's message above.")
        elif action == "ability":
            lines.append(self._use_ability(state, combat, me, ability_id, target_id, advantage))
        else:
            raise CombatError("Unknown action.")
        if not self._finished(combat):
            self._advance(combat)
            lines += self._others_until_player(combat)
        self._sync_player(state)
        return self._wrap(state, lines, round_no)

    def _use_ability(self, state: dict, combat: dict, me: dict, ability_id: str, target_id: str, advantage: str) -> str:
        """The player spends a resource on an ability: an attack, a heal or another effect."""
        from .resources import ResourceError, cost_text, pay, pools_line
        ability = next((a for a in state.get("abilities") or [] if a["id"] == ability_id), None)
        if not ability:
            raise CombatError("That ability is not on your sheet.")
        target = None
        if ability["kind"] == "attack":
            target = self._get(combat, target_id)
            if target["hp"] <= 0:
                raise CombatError(f"{target['name']} is already down.")
        try:
            pay(state, ability["costs"])
        except ResourceError as exc:
            raise CombatError(str(exc)) from exc
        spent = f" (\u2212{cost_text(ability['costs'])} \u2192 {pools_line(state)})" if ability["costs"] else ""
        if ability["kind"] == "attack":
            att = dict(me)
            if ability["bonus"] is not None:
                att["attack_bonus"] = ability["bonus"]
            if ability["dice"]:
                att["damage"] = ability["dice"] if combat["system"] != "pool" else str(self.dice.roll(ability["dice"]).total)
            return self._attack(combat, att, target, advantage if advantage in ("advantage", "disadvantage") else "",
                                head=f"**{me['name']} uses {ability['name']} on {target['name']}**{spent}")
        if ability["kind"] == "heal" and ability["dice"]:
            r = self.dice.roll(ability["dice"])
            me["hp"] = min(me["max_hp"], me["hp"] + max(0, r.total))
            return f"**{me['name']} uses {ability['name']}**{spent}\n\U0001F49A heals {r.total} ({ability['dice']}) \u2192 {me['hp']}/{me['max_hp']} HP"
        return f"**{me['name']} uses {ability['name']}**{spent}\n\u2728 {ability['description'] or 'See the player message.'}"

    def enemies_act(self, state: dict) -> tuple[dict, str]:
        combat = state.get("combat") or {}
        if not combat.get("active"):
            raise CombatError("There is no fight going on.")
        round_no = combat["round"]
        if self.current(combat)["side"] == "player":
            self._advance(combat)
        lines = self._others_until_player(combat)
        self._sync_player(state)
        return self._wrap(state, lines or ["Nobody else acts this round."], round_no)

    def _others_until_player(self, combat: dict) -> list[str]:
        lines = []
        for _ in range(len(combat["order"]) * 2):
            if self._finished(combat):
                break
            c = self.current(combat)
            if c["side"] == "player":
                if c["hp"] > 0:
                    break
                self._advance(combat)
                continue
            if c["hp"] <= 0:
                self._advance(combat)
                continue
            foes = [x for x in combat["combatants"] if x["hp"] > 0 and ((x["side"] == "enemy") != (c["side"] == "enemy"))]
            if foes:
                target = min(foes, key=lambda f: (distance(c["x"], c["y"], f["x"], f["y"]), f["hp"]))
                moved = ""
                spell = c.get("spell")
                casting = bool(spell and c.get("mp", 0) >= spell["cost"])
                reach = max(c.get("range", 1), spell["range"]) if casting else c.get("range", 1)
                if distance(c["x"], c["y"], target["x"], target["y"]) > reach:
                    occupied = {(o["x"], o["y"]) for o in combat["combatants"] if o["hp"] > 0 and o["id"] != c["id"]}
                    nx, ny = path_step(combat["grid"].get("tiles") or [], (c["x"], c["y"]), (target["x"], target["y"]),
                                       occupied, c.get("speed", 6))
                    if (nx, ny) != (c["x"], c["y"]):
                        steps = distance(c["x"], c["y"], nx, ny)
                        c["x"], c["y"] = nx, ny
                        moved = f"🏃 {c['name']} moves {steps} squares ({steps * 5} ft) toward {target['name']}."
                if casting and distance(c["x"], c["y"], target["x"], target["y"]) <= spell["range"]:
                    c["mp"] -= spell["cost"]
                    block = self._attack(combat, {**c, "damage": spell["damage"]}, target, head=(
                        f"**{c['name']} casts {spell['name']} at {target['name']}** ({c['mp_name']} {c['mp']}/{c['mp_max']})"))
                    if moved:
                        head, _, rest = block.partition("\n")
                        block = f"{head}\n{moved}\n{rest}"
                    lines.append(block)
                elif distance(c["x"], c["y"], target["x"], target["y"]) <= c.get("range", 1):
                    drained = f" ({c['mp_name']} spent: no more {spell['name']})" if spell and not casting else ""
                    block = self._attack(combat, c, target, head=f"**{c['name']} attacks {target['name']}**{drained}")
                    if moved:  # header first, then the move, then the roll
                        head, _, rest = block.partition("\n")
                        block = f"{head}\n{moved}\n{rest}"
                    lines.append(block)
                elif moved:
                    lines.append(f"**{c['name']} closes in**\n{moved}")
            self._advance(combat)
        return lines

    def _wrap(self, state: dict, lines: list[str], round_no: int) -> tuple[dict, str]:
        combat = state["combat"]
        if combat["round"] > round_no:  # new round(s): resources that refill every round do so
            from .resources import regenerate
            back = regenerate(state, "round", combat["round"] - round_no)
            if back:
                lines.append("\U0001F504 " + ", ".join(back))
        done = self._finished(combat)
        text = f"⚔️ **Round {round_no}**\n\n" + "\n\n".join(lines)
        if done:
            state, end_line = self.end(state, done)
            text += "\n\n🏁 " + end_line.replace("⚔️ ", "")
        combat["log"] = (combat.get("log", []) + lines)[-30:]
        return state, text

    # ------------------------------------------------------------------ edits from the panel
    def edit(self, state: dict, cid: str, hp: int | None = None, conditions: list[str] | None = None,
             x: int | None = None, y: int | None = None) -> dict:
        combat = state.get("combat") or {}
        if not combat.get("active"):
            raise CombatError("There is no fight going on.")
        c = self._get(combat, cid)
        if hp is not None:
            c["hp"] = int(clamp(as_int(hp, c["hp"]), 0, c["max_hp"]))
        if conditions is not None:
            c["conditions"] = [k for k in conditions if k in CONDITIONS]
        if x is not None and y is not None:
            gx, gy = as_int(x, c["x"]), as_int(y, c["y"])
            w, h = combat["grid"]["w"], combat["grid"]["h"]
            if not (0 <= gx < w and 0 <= gy < h):
                raise CombatError("That square is outside the map.")
            if any(o["id"] != cid and o["x"] == gx and o["y"] == gy and o["hp"] > 0 for o in combat["combatants"]):
                raise CombatError("That square is taken.")
            if blocked(combat["grid"].get("tiles") or [], gx, gy):
                raise CombatError("You cannot stand there (wall, tree, rock, crate or deep water).")
            c["x"], c["y"] = gx, gy
        if c["side"] == "player":
            self._sync_player(state)
        return state


def describe_combat(combat: dict) -> str:
    """For the GM's private notes while a fight is on."""
    if not combat or not combat.get("active"):
        return ""
    cur = next((c for c in combat["combatants"] if c["id"] == combat["order"][combat["turn"] % len(combat["order"])]), None)
    lines = [f"Round {combat['round']}." + (f" It is {cur['name']}'s turn." if cur else "")]
    for cid in combat["order"]:
        c = next(x for x in combat["combatants"] if x["id"] == cid)
        state = "DOWN" if c["hp"] <= 0 else f"{c['hp']}/{c['max_hp']} HP"
        conds = f" [{', '.join(c['conditions'])}]" if c["conditions"] else ""
        mp = f", {c['mp_name']} {c['mp']}/{c['mp_max']} ({c['spell']['name']} costs {c['spell']['cost']})" if c.get("spell") else ""
        lines.append(f"- {c['name']} ({c['side']}): {state}{mp}{conds}")
    return "\n".join(lines)


COMBAT_RULES = (
    "A fight is going on and the APP tracks it: initiative, movement, hits, damage and HP. The ⚔️ block in the player's "
    "message lists verified results, one action per paragraph. Narrate the actions IN THE SAME ORDER, one short vivid "
    "paragraph per action. Never change who hit, the damage or the HP, never invent extra attacks or damage, never repeat "
    "the dice numbers, and never declare a combatant dead or defeated unless the ⚔️ block says so. "
    "End your reply by asking what the player does next."
)


async def suggest_fight(llm, system: str, scene: str, rules: str = "") -> dict:
    """Enemies and a map type for the current scene: {"enemies": [...], "map": {"type", "features"}}."""
    from .maps import FEATURES, TYPES

    enemies, raw = await _suggest(llm, system, scene, rules, with_map=True)
    m = raw.get("map") if isinstance(raw, dict) and isinstance(raw.get("map"), dict) else {}
    kind = str(m.get("type", "")).lower().strip()
    feats = [f for f in (m.get("features") if isinstance(m.get("features"), list) else []) if f in FEATURES][:3]
    return {"enemies": enemies, "map": {"type": kind if kind in TYPES else "field", "features": feats}}


async def suggest_enemies(llm, system: str, scene: str, rules: str = "") -> list[dict]:
    """Ask the model which enemies the current scene has, with numbers for the chosen preset (you confirm them)."""
    return (await _suggest(llm, system, scene, rules))[0]


async def _suggest(llm, system: str, scene: str, rules: str = "", with_map: bool = False) -> tuple[list[dict], dict]:
    from .maps import FEATURES, TYPES
    from .util import extract_json

    if system == "pool":
        fields = ("name, count, hp (health boxes, usually 4-10), pool (dice for attacks, 3-9), defense (dice to avoid hits, 2-7), "
                  "damage (weapon bonus 0-4)")
    else:
        fields = ("name, count, hp (5e hit points), ac (armor class), attack_bonus, damage (dice like 1d6+2), init_bonus (DEX modifier)")
    prompt = (
        "You prepare a fight for a tabletop roleplaying game. Read the scene and list the enemies who fight the player now.\n"
        f"Answer with ONE JSON object: {{\"enemies\": [ {{{fields}, range (1 = melee, 12+ for bows and spells), and ONLY for "
        f"casters: mp (their mana or other power pool), mp_name, spell {{name, cost, damage, range}} }} ]"
        + (f", \"map\": {{\"type\": one of {list(TYPES)}, \"features\": up to 3 of {list(FEATURES)}}}" if with_map else "")
        + "}. Use plausible, fair numbers for a level-appropriate fight. Group identical enemies with count. At most 6 entries.\n"
        + (f"\nRulebook passages that may help:\n{truncate(rules, 1800)}\n" if rules else "")
        + f"\nSCENE:\n{truncate(scene, 2500)}\n\nOutput the JSON object now."
    )
    raw = await llm.chat([{"role": "user", "content": prompt}], max_tokens=500, temperature=0.4)
    data = extract_json(raw)
    items = data.get("enemies") if isinstance(data, dict) else data if isinstance(data, list) else None
    if not isinstance(items, list) or not items:
        raise CombatError("The model did not suggest any enemies. Fill them in yourself.")
    out = []
    for raw_item in items[:6]:
        if isinstance(raw_item, dict) and str(raw_item.get("name", "")).strip():
            c = _combatant(raw_item, "enemy", system, 0)
            c["count"] = max(1, min(8, as_int(raw_item.get("count", 1), 1)))
            for k in ("id", "side", "conditions", "x", "y", "init", "current_hp", "mp_current"):
                c.pop(k, None)
            c["hp"] = c.pop("max_hp")
            c.pop("mp_max", None)  # "mp" stays: the caster's full pool
            out.append(c)
    if not out:
        raise CombatError("The model did not suggest any enemies. Fill them in yourself.")
    return out, data if isinstance(data, dict) else {}
