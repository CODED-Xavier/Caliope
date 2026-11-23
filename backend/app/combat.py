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

import math
import random
import re
import uuid

from .dice import DiceError, DiceRoller
from .maps import blocked, clean_tiles, distance, has_cover, open_cells, path_step, walk_cost
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


class AreaRisk(CombatError):
    """The area would catch you or an ally: the player is asked first and may cast anyway (`risk`)."""

    def __init__(self, message: str, who: list[str]):
        super().__init__(message)
        self.who = who


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
    sheet = state.get("character5e_sheet")
    if sheet:  # a 5e sheet (app/dnd5e): the real weapon, AC and initiative
        melee = [a for a in sheet.get("attacks") or [] if "ft" in a.get("range", "") and "/" not in a.get("range", "")]
        att = (melee or sheet.get("attacks") or [None])[0]
        out = {"ac": as_int(sheet.get("ac", 10), 10), "init_bonus": as_int(sheet.get("initiative", 0), 0), "hp": as_int(p["hp"]["max"], 10)}
        if sheet.get("class") == "Rogue":  # Sneak Attack: once a turn, with advantage or an ally next to the target
            from .dnd5e.magic import sneak_dice
            out["sneak"] = sneak_dice(as_int(sheet.get("level", 1), 1))
        if att:
            out.update(attack_bonus=att["bonus"], damage=att["damage"], weapon=att["name"])
        else:
            strength = ability_mod(stats.get("STR", 10))  # an unarmed strike: 1 + STR, with proficiency
            out.update(attack_bonus=sheet.get("prof", 2) + strength, damage=f"1{strength:+d}" if strength else "1", weapon="Unarmed Strike")
        return out
    mod = max(ability_mod(stats.get("STR", 10)), ability_mod(stats.get("DEX", 10)))
    prof = 2 + max(0, as_int(p.get("level", 1), 1) - 1) // 4
    return {"attack_bonus": mod + prof, "damage": f"1d8{mod:+d}" if mod else "1d8", "ac": as_int(p.get("ac", 10), 10),
            "init_bonus": ability_mod(stats.get("DEX", 10)), "hp": as_int(p["hp"]["max"], 10)}


DICE_RE = re.compile(r"\d{1,2}d\d{1,3}([+-]\d{1,2})?")


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
        "weapon": truncate(str(raw.get("weapon") or ""), 40),
        "range": max(1, min(30, as_int(raw.get("range", 1), 1))),   # squares: 1 = melee, more = ranged
        "speed": max(1, min(12, as_int(raw.get("speed", 6), 6))),   # squares per turn (6 = 30 ft)
    }
    if raw.get("sneak") and DICE_RE.fullmatch(str(raw["sneak"])):
        c["sneak"] = str(raw["sneak"])
    if isinstance(raw.get("saves"), dict):  # saving throw bonuses (a bestiary sheet), for spells with a save
        c["saves"] = {str(k)[:3].lower(): max(-5, min(20, as_int(v, 0))) for k, v in raw["saves"].items()}
    if side == "ally" and raw.get("companion"):  # app/party.py: Calíope plays them (healers heal, the others attack)
        c["companion"] = True
        c["role"] = str(raw.get("role") or "fighter")
        if raw.get("heal"):
            c["heal"], c["heals_left"] = _dice_ok(raw["heal"], "1d8+3"), max(0, as_int(raw.get("heals", 0), 0))
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


def me_down(combat: dict) -> dict:
    return next(c for c in combat["combatants"] if c["side"] == "player")


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
                                                 "painted": bool((battle_map or {}).get("painted")),
                                                 **_picture_geometry(battle_map)},
                  "log": log[-30:]}
        combat["spent"] = {"action": False, "bonus": False, "attacked": False}
        combat["turn_lines"] = []
        state["combat"] = combat
        order = ", ".join(c["name"] for c in people)
        foes = ", ".join(f"{c['name']} ({c['hp']} HP)" for c in people if c["side"] == "enemy")
        line = f"⚔️ Combat starts! Turn order: {order}. Enemies: {foes}."
        first = self._others_until_player(combat)  # whoever is faster than the player acts now, rolled by the app
        combat["moved"] = 0
        if first:
            self._sync_player(state)
            combat["log"] = (combat["log"] + first)[-30:]
            line += "\n\n" + "\n\n".join(first)
            done = self._finished(combat)
            if done == "you have fallen" and me_down(combat).get("dying"):
                line += "\n\n" + self._fall_out(combat, me_down(combat))
                self._sync_player(state)
            if done:
                state, end_line = self.end(state, done)
                line += "\n\n🏁 " + end_line.replace("⚔️ ", "")
        if combat.get("active"):
            line += f"\n\n➡️ {self.current(combat)['name']}'s turn."
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
        group = state.get("party") or {}
        for c in state["combat"]["combatants"]:  # companions' HP lasts after the fight
            if c.get("companion") and c["name"] in group:
                group[c["name"]]["hp"] = int(clamp(c["hp"], 0, group[c["name"]]["max_hp"]))

    def _advance(self, combat: dict) -> None:
        """Next living combatant; a new round starts after the last one."""
        n = len(combat["order"])
        combat.pop("last_hit", None)
        for _ in range(n):
            combat["turn"] += 1
            if combat["turn"] >= n:
                combat["turn"] = 0
                combat["round"] += 1
            cur = self.current(combat)
            if "dodging" in cur["conditions"]:  # a Dodge lasts until the dodger's own next turn
                cur["conditions"].remove("dodging")
            if cur["hp"] > 0 or cur.get("dying"):  # a dying player still has a turn: their death save
                if cur["side"] == "player":
                    combat["moved"] = 0  # a fresh turn: the player's full speed again
                    combat["spent"] = {"action": False, "bonus": False, "attacked": False}
                    combat["extra_actions"] = 0
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
            after = self._hurt(combat, target, dmg, crit=a["critical"])
            crit = " (CRITICAL)" if a["critical"] else ""
            return (f"{head}\n{roll} → **HIT**{crit}\n💥 {dmg} damage → {target['name']} {target['hp']}/{target['max_hp']} HP"
                    + after)

        mode = advantage
        if "dodging" in target["conditions"] or "invisible" in target["conditions"]:
            mode = "disadvantage" if mode != "advantage" else ""
        if any(x in target["conditions"] for x in ("prone", "restrained", "stunned", "blinded")) and mode != "disadvantage":
            mode = "advantage"
        if any(x in att["conditions"] for x in ("poisoned", "frightened", "blinded", "restrained", "prone")):
            mode = "disadvantage" if mode != "advantage" else ""
        ac = target["ac"] + (2 if cover else 0) + (5 if target.get("shielded") == combat["round"] else 0)
        expr = "1d20" + (f"{att['attack_bonus']:+d}" if att["attack_bonus"] else "") + (f" {mode}" if mode else "")
        r = self.dice.roll(expr)
        hit = r.natural != 1 and (r.natural == 20 or r.total >= ac)
        reacted = ""
        if hit and r.natural != 20 and target["side"] == "player" and r.total < ac + 5 and self._can_react(combat, target, "shield"):
            # Shield (reaction, a 1st-level slot): +5 AC until your next turn, this attack included
            target["shielded"] = combat["round"]
            combat["reaction_round"] = combat["round"]
            combat.setdefault("auto_spent", []).append("slot")
            ac += 5
            hit = False
            reacted = f" · 🛡 {target['name']} casts Shield (reaction): AC {ac}"
        tag = " (advantage)" if r.mode == "advantage" else " (disadvantage)" if r.mode == "disadvantage" else ""
        roll = (f"🎲 d20({r.natural}) {att['attack_bonus']:+d} = {r.total} vs AC {ac}"
                + (" (cover +2)" if cover else "") + tag)
        if not hit:
            return f"{head}\n{roll} → **{'natural 1, ' if r.natural == 1 else ''}MISS**{reacted}"
        dmg_expr = att["damage"]
        extra = []
        if att.get("raging") and att.get("range", 1) <= 1:  # Rage: a bonus on Strength melee damage
            dmg_expr += f"+{att.get('rage_bonus', 2)}"
            extra.append("Rage")
        if att.get("sneak") and att["side"] == "player" and not combat.setdefault("spent", {}).get("sneak") and (
                r.mode == "advantage" or any(o["side"] in ("ally",) and o["hp"] > 0 and distance(o["x"], o["y"], target["x"], target["y"]) <= 1
                                             for o in combat["combatants"])):
            dmg_expr += f"+{att['sneak']}"
            combat["spent"]["sneak"] = True
            extra.append("Sneak Attack")
        if r.natural == 20:  # critical: double the dice
            dmg_expr = re.sub(r"(\d*)d(\d+)", lambda m: f"{2 * int(m.group(1) or 1)}d{m.group(2)}", dmg_expr)
        d = self.dice.roll(dmg_expr)
        dmg = max(1, d.total)
        if att["side"] == "player":  # for Divine Smite: the last hit this turn
            combat["last_hit"] = {"target": target["id"], "melee": att.get("range", 1) <= 1, "crit": r.natural == 20}
        if target["side"] == "player" and self._can_react(combat, target, "uncanny"):  # Uncanny Dodge: half damage
            combat["reaction_round"] = combat["round"]
            dmg = max(1, dmg // 2)
            reacted = f" · 🌀 {target['name']} uses Uncanny Dodge (reaction): half damage"
        if extra:
            dmg_expr += f" · {', '.join(extra)}"
        after = self._hurt(combat, target, dmg, crit=r.natural == 20) + reacted
        crit = "CRITICAL HIT" if r.natural == 20 else "HIT"
        return (f"{head}\n{roll} → **{crit}**\n💥 {dmg} damage ({dmg_expr}) → {target['name']} {target['hp']}/{target['max_hp']} HP"
                + after)

    @staticmethod
    def _can_react(combat: dict, me: dict, what: str) -> bool:
        """An automatic reaction the player turned on (🛡 Shield with a slot left, 🌀 Uncanny Dodge), once a round."""
        auto = combat.get("auto_reactions") or {}
        if not auto.get(what) or me["hp"] <= 0 or combat.get("reaction_round") == combat["round"]:
            return False
        if what == "shield":
            return auto.get("slots", 0) > len([x for x in combat.get("auto_spent", []) if x == "slot"])
        return True

    def _area_targets(self, combat: dict, me: dict, target: dict, area: dict) -> list[dict]:
        """Everyone a spell's area covers (the map's 🔥 tool, the same squares)."""
        size = max(5, as_int(area.get("size"), 5)) / 5
        shape, origin = area.get("shape"), area.get("origin")
        out = []
        for c in combat["combatants"]:
            if c["hp"] <= 0 or (c is me and origin == "self"):
                continue
            if shape == "sphere":
                ox, oy = (me["x"], me["y"]) if origin == "self" else (target["x"], target["y"])
                inside = math.hypot(c["x"] - ox, c["y"] - oy) <= size + 0.01
            elif shape == "cube" and origin == "point":
                n = max(1, round(size))
                x0 = target["x"] if target["x"] >= me["x"] else target["x"] - n + 1
                y0 = target["y"] if target["y"] >= me["y"] else target["y"] - n + 1
                inside = x0 <= c["x"] < x0 + n and y0 <= c["y"] < y0 + n
            elif shape == "cube":
                n = max(1, round(size))
                sx, sy = (target["x"] > me["x"]) - (target["x"] < me["x"]), (target["y"] > me["y"]) - (target["y"] < me["y"])
                x0 = me["x"] + 1 if sx > 0 else me["x"] - n if sx < 0 else me["x"] - (n - 1) // 2
                y0 = me["y"] + 1 if sy > 0 else me["y"] - n if sy < 0 else me["y"] - (n - 1) // 2
                inside = (sx or sy) and x0 <= c["x"] < x0 + n and y0 <= c["y"] < y0 + n
            else:  # cone or line from the caster toward the target
                dx, dy = target["x"] - me["x"], target["y"] - me["y"]
                length = math.hypot(dx, dy) or 1
                vx, vy = c["x"] - me["x"], c["y"] - me["y"]
                along = (vx * dx + vy * dy) / length
                across = abs(vx * dy - vy * dx) / length
                half = max(5, as_int(area.get("width"), 5)) / 10
                inside = 0 < along <= size + 0.01 and (across <= half + 0.01 if shape == "line" else across <= along / 2 + 0.01)
            if inside:
                out.append(c)
        return out

    def _cast(self, combat: dict, me: dict, target_id: str, name: str, info: dict) -> str:
        """A spell from the 5e sheet: its attack roll or saving throws, its damage (once, for everyone in the area),
        or its healing. What the app can't roll (Hold Person's effect, a summon), the Aedo narrates."""
        slot = f" (level {info['slot']} slot)" if info.get("slot") else ""
        target = self._get(combat, target_id) if target_id else None
        head = f"**{me['name']} casts {name}" + (f" at {target['name']}" if target and target is not me else "") + f"**{slot}"
        kind = info.get("kind")
        if kind == "attack":
            if not target:
                raise CombatError(f"Choose who {name} is aimed at.")
            return self._attack(combat, {**me, "attack_bonus": info["attack"], "damage": info["dice"], "range": 99, "raging": False, "sneak": ""},
                                target, head=head)
        if kind == "heal":
            who = target if target and target["side"] != "enemy" else me
            r = self.dice.roll(info["dice"])
            before = who["hp"]
            who["hp"] = min(who["max_hp"], who["hp"] + max(1, r.total))
            if who["hp"] > 0 and who.get("dying"):
                who.update(dying=False, stable=False, death={"ok": 0, "fail": 0})
            return f"{head}\n💚 +{who['hp'] - before} HP ({info['dice']}) → {who['name']} {who['hp']}/{who['max_hp']} HP"
        sculpted: list[dict] = []
        if kind == "save":
            if info.get("area") and target:
                hit = self._area_targets(combat, me, target, info["area"])
                friends = [c for c in hit if c is me or c["side"] in ("player", "ally")]
                # Sculpt Spells (Evocation): 1 + the spell's level of them pass the save and take no damage, you first
                sculpted = friends[: max(0, as_int(info.get("sculpt"), 0))]
                exposed = [c for c in friends if c not in sculpted]
                if exposed and not info.get("risk"):
                    names = ["you" if c is me else c["name"] for c in exposed]
                    who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
                    raise AreaRisk(f"{who[0].upper() + who[1:]} would be inside {name}'s area ({info['area'].get('size', 5)} ft around "
                                   f"{target['name']}). Cast it anyway?", [c["name"] for c in exposed])
            elif target:
                hit = [target]
            else:
                raise CombatError(f"Choose who {name} is aimed at.")
            if not info.get("dice"):  # a save with no damage (Hold Person, Sleep…): who resists, who is affected
                outcome = []
                for c in hit:
                    if c in sculpted:
                        outcome.append(f"{c['name']} is spared (Sculpt Spells)")
                        continue
                    bonus = (c.get("saves") or {}).get(info["save"], 0)
                    sv = self.dice.roll(f"1d20{bonus:+d}" if bonus else "1d20")
                    outcome.append(f"{c['name']} {'resists' if sv.total >= info['dc'] else 'is affected'} ({sv.total})")
                return f"{head}\n🎯 DC {info['dc']} {info['save'].upper()} save: " + ", ".join(outcome)
            r = self.dice.roll(info["dice"])
            lines = [f"{head}\n💥 {r.total} {info.get('dtype') or ''} damage ({info['dice']}) · DC {info['dc']} {info['save'].upper()} save:".replace("  ", " ")]
            for c in hit or []:
                if c in sculpted:
                    lines.append(f"- {c['name']}: ✨ spared, the spell bends around them (Sculpt Spells) → no damage")
                    continue
                bonus = (c.get("saves") or {}).get(info["save"], 0)
                sv = self.dice.roll(f"1d20{bonus:+d}" if bonus else "1d20")
                ok = sv.total >= info["dc"]
                dmg = (r.total // 2 if info.get("half") else 0) if ok else r.total
                after = self._hurt(combat, c, dmg) if dmg else ""
                lines.append(f"- {c['name']}: d20({sv.natural}){bonus:+d} = {sv.total} → {'saved' if ok else 'failed'}"
                             + (f" → {dmg} → {c['hp']}/{c['max_hp']} HP" if dmg else " → no damage") + after)
            if not hit:
                lines.append("- nobody inside")
            return "\n".join(lines)
        return f"{head}\n✨ The Aedo narrates what {name} does."

    def _smite(self, combat: dict, me: dict, info: dict) -> str:
        last = combat.get("last_hit")
        target = self._get(combat, last["target"]) if last else None
        if not target or not last.get("melee"):
            raise CombatError("Divine Smite comes right after you hit with a melee weapon.")
        dice = info["dice"]
        if last.get("crit"):  # a critical hit doubles the smite's dice too
            dice = re.sub(r"(\d*)d(\d+)", lambda m: f"{2 * int(m.group(1) or 1)}d{m.group(2)}", dice)
        combat.pop("last_hit", None)  # one smite per hit
        r = self.dice.roll(dice)
        after = self._hurt(combat, target, max(1, r.total))
        return (f"**{me['name']}'s Divine Smite** (level {info['slot']} slot)\n"
                f"💥 {r.total} radiant damage ({dice}) → {target['name']} {target['hp']}/{target['max_hp']} HP{after}")

    def _hurt(self, combat: dict, target: dict, dmg: int, crit: bool = False) -> str:
        """Damage lands. A player at 0 HP is dying (5e death saves); a hit while dying is a failed save (a critical, two)."""
        if target["side"] == "player" and target["hp"] <= 0 and not target.get("dead"):
            death = target.setdefault("death", {"ok": 0, "fail": 0})
            death["fail"] += 2 if crit else 1
            target["stable"] = False
            target["dying"] = True
            if death["fail"] >= 3:
                target["dying"], target["dead"] = False, True
                return f" · 💀 **{target['name']} dies.**"
            return f" · 💀 a hit while dying: death save failure ({death['fail']}/3)"
        if target.get("raging"):  # Rage: resistance to weapon damage
            dmg = max(1, dmg // 2)
        target["hp"] = max(0, target["hp"] - dmg)
        if target["hp"] > 0:
            return ""
        if target["side"] == "player":
            target.update(dying=True, stable=False, death={"ok": 0, "fail": 0})
            return f" · **{target['name']} falls, dying!** (death saves each turn)"
        return f" · **{target['name']} falls unconscious!**" if target["side"] == "ally" else f" · **{target['name']} is defeated!**"

    def _death_save(self, combat: dict, me: dict) -> str:
        """One death saving throw: 10+ succeeds; a natural 20 brings them back at 1 HP; a natural 1 is two failures."""
        r = self.dice.roll("1d20")
        death = me.setdefault("death", {"ok": 0, "fail": 0})
        if r.natural == 20:
            me.update(hp=1, dying=False, stable=False, death={"ok": 0, "fail": 0})
            return f"💀 **{me['name']}'s death save**: d20(20) → **natural 20!** {me['name']} gets back up with 1 HP."
        if r.natural == 1:
            death["fail"] += 2
            word = "natural 1: two failures"
        elif r.total >= 10:
            death["ok"] += 1
            word = "success"
        else:
            death["fail"] += 1
            word = "failure"
        tail = f" (✔ {death['ok']}/3 · ✖ {min(3, death['fail'])}/3)"
        if death["fail"] >= 3:
            me.update(dying=False, dead=True)
            return f"💀 **{me['name']}'s death save**: d20({r.natural}) → {word}{tail}. **{me['name']} dies.**"
        if death["ok"] >= 3:
            me.update(dying=False, stable=True)
            return f"💀 **{me['name']}'s death save**: d20({r.natural}) → {word}{tail}. **{me['name']} is stable** (unconscious)."
        return f"💀 **{me['name']}'s death save**: d20({r.natural}) → {word}{tail}"

    def _fall_out(self, combat: dict, me: dict) -> str:
        """Nobody on the player's side is standing: the remaining saves decide whether they are left alive."""
        lines = []
        for _ in range(12):
            if not me.get("dying"):
                break
            lines.append(self._death_save(combat, me))
        if me.get("stable") or me["hp"] > 0:
            me["hp"] = max(1, me["hp"])
            lines.append(f"🩹 {me['name']} survives: left for dead or captured, waking later with {me['hp']} HP.")
        return "\n".join(lines)

    def _companion_heal(self, combat: dict, c: dict) -> str:
        """A healer's turn: heal the dying player first, then whoever is lowest below half HP (while heals remain)."""
        if not c.get("heal") or c.get("heals_left", 0) <= 0:
            return ""
        side = [x for x in combat["combatants"] if x["side"] in ("player", "ally") and not x.get("dead")]
        dying = [x for x in side if x["side"] == "player" and x["hp"] <= 0]
        hurt = [x for x in side if 0 < x["hp"] < x["max_hp"] / 2]
        target = (dying or sorted(hurt, key=lambda x: x["hp"] / x["max_hp"]) or [None])[0]
        if target is None:
            return ""
        amount = max(1, self.dice.roll(c["heal"]).total)
        was_down = target["hp"] <= 0
        target["hp"] = min(target["max_hp"], max(0, target["hp"]) + amount)
        if target["side"] == "player":
            target.update(dying=False, stable=False, death={"ok": 0, "fail": 0})
        c["heals_left"] -= 1
        back = f" · **{target['name']} is back on their feet!**" if was_down else ""
        return (f"**{c['name']} heals {target['name']}** ({c['heals_left']} heals left)\n"
                f"💚 +{amount} HP ({c['heal']}) → {target['name']} {target['hp']}/{target['max_hp']} HP{back}")

    def _finished(self, combat: dict) -> str:
        if all(c["hp"] <= 0 for c in combat["combatants"] if c["side"] == "enemy"):
            return "all enemies are down"
        if any(c.get("dead") for c in combat["combatants"] if c["side"] == "player"):
            return "you have fallen"
        if all(c["hp"] <= 0 for c in combat["combatants"] if c["side"] in ("player", "ally")):
            return "you have fallen"
        return ""

    # ------------------------------------------------------------------ actions
    # ---------------------------------------------------------------- the player's turn: action, bonus, move, reaction
    @staticmethod
    def _martial_arts(state: dict) -> dict | None:
        """The Unarmed Strike a Monk can make as a bonus action after taking the Attack action."""
        sheet = state.get("character5e_sheet") or {}
        if not sheet.get("martial_arts"):
            return None
        return next((a for a in sheet.get("attacks") or [] if a.get("name") == "Unarmed Strike"), None)

    def turn_left(self, state: dict) -> str:
        """What the player can still do this turn, said after each step."""
        combat = state["combat"]
        spent = combat.setdefault("spent", {"action": False, "bonus": False, "attacked": False})
        me = next(c for c in combat["combatants"] if c["side"] == "player")
        left = []
        if not spent["action"] or combat.get("extra_actions"):
            left.append("your action" if not spent["action"] else "one more action")
        if not spent["bonus"]:
            left.append("a bonus action (Martial Arts strike)" if self._martial_arts(state) and spent["attacked"] else "a bonus action")
        move = max(0, me.get("speed", 6) - combat.get("moved", 0))
        if move:
            left.append(f"{move * 5} ft of movement")
        return f"➡️ Still {me['name']}'s turn: " + (", ".join(left) or "nothing left") + ". End your turn when you're done."

    def _check_my_turn(self, state: dict) -> tuple[dict, dict]:
        combat = state.get("combat") or {}
        if not combat.get("active"):
            raise CombatError("There is no fight going on.")
        me = next(c for c in combat["combatants"] if c["side"] == "player")
        if self.current(combat)["id"] != me["id"]:
            raise CombatError(f"It is {self.current(combat)['name']}'s turn.")
        if me["hp"] <= 0:
            raise CombatError("You are down: your death saves are rolled on your turns while your companions fight on. "
                              "Use “Others act” to play the round.")
        combat.setdefault("spent", {"action": False, "bonus": False, "attacked": False})
        combat.setdefault("turn_lines", [])
        return combat, me

    def _do(self, state: dict, combat: dict, me: dict, action: str, target_id: str, advantage: str, ability_id: str) -> str:
        """One part of the player's turn, checked against what is left (one action, one bonus action)."""
        spent = combat["spent"]
        if action == "bonus_attack":
            punch = self._martial_arts(state)
            if not punch:
                raise CombatError("You have no attack to make as a bonus action (a Monk's Martial Arts gives one).")
            if spent["bonus"]:
                raise CombatError("You already used your bonus action this turn.")
            if not spent["attacked"]:
                raise CombatError("Martial Arts: take the Attack action first, then strike again as a bonus action.")
            target = self._get(combat, target_id)
            if target["hp"] <= 0:
                raise CombatError(f"{target['name']} is already down.")
            spent["bonus"] = True
            att = {**me, "attack_bonus": as_int(punch.get("bonus"), 0), "damage": str(punch.get("damage") or "1")}
            return self._attack(combat, att, target, advantage if advantage in ("advantage", "disadvantage") else "",
                                head=f"**{me['name']} strikes {target['name']} (Unarmed Strike, bonus action)**")
        self._spend_action(combat)
        if action == "attack":
            spent["attacked"] = True
        return self._act(state, combat, me, action, target_id, advantage, ability_id)

    @staticmethod
    def _spend_action(combat: dict) -> None:
        spent = combat["spent"]
        if spent["action"]:
            if combat.get("extra_actions"):  # Action Surge and the like
                combat["extra_actions"] -= 1
                return
            raise CombatError("You already used your action this turn. You can still use a bonus action, move, or end your turn.")
        spent["action"] = True

    def _contest(self, state: dict, me: dict, target: dict, what: str) -> str:
        """Grapple or Shove: your Strength (Athletics) against the target's Athletics or Acrobatics (ties: nothing happens)."""
        skills = (state.get("character5e_sheet") or {}).get("skills") or {}
        mine = as_int((skills.get("athletics") or {}).get("bonus"), ability_mod((state["player"].get("stats") or {}).get("STR", 10)))
        theirs = as_int(target.get("athletics"), max(0, as_int(target.get("attack_bonus"), 2) - 2))
        a, b = self.dice.roll(f"1d20{mine:+d}" if mine else "1d20"), self.dice.roll(f"1d20{theirs:+d}" if theirs else "1d20")
        won = a.total > b.total
        if won:
            cond = "grappled" if what == "grapple" else "prone"
            if cond not in target["conditions"]:
                target["conditions"].append(cond)
        result = ("GRAPPLED" if what == "grapple" else "KNOCKED PRONE") if won else "fails"
        return (f"**{me['name']} tries to {what} {target['name']}**\n🤼 Athletics d20({a.natural}) {mine:+d} = {a.total} vs "
                f"d20({b.natural}) {theirs:+d} = {b.total} → **{result}**")

    def use_option(self, state: dict, option: dict, target_id: str = "", advantage: str = "") -> tuple[dict, str]:
        """One option from the 5e list (Dash, Grapple, Second Wind, a spell…): its cost is spent and held until the turn
        ends (the reaction until the round ends); what the app can roll, it rolls; the rest the Aedo narrates."""
        kind, cost, name = option.get("kind", ""), option.get("cost", "action"), option.get("name", "")
        if kind in ("attack", "dodge", "bonus_attack"):
            return self.player_step(state, kind, target_id, advantage)
        combat = state.get("combat") or {}
        if not combat.get("active"):
            raise CombatError("There is no fight going on.")
        kept = {"spent": dict(combat.get("spent") or {}), "reaction_round": combat.get("reaction_round"),
                "extra_actions": combat.get("extra_actions", 0), "moved": combat.get("moved", 0)}
        try:
            if cost == "reaction":  # a reaction can come on someone else's turn: once per round
                me = next(c for c in combat["combatants"] if c["side"] == "player")
                if me["hp"] <= 0:
                    raise CombatError("You are unconscious.")
                if combat.get("reaction_round") == combat["round"]:
                    raise CombatError("You already used your reaction this round. It comes back at the start of your next turn.")
                combat["reaction_round"] = combat["round"]
                combat.setdefault("turn_lines", [])
            else:
                combat, me = self._check_my_turn(state)
                if cost == "action":
                    self._spend_action(combat)
                elif cost == "bonus":
                    if combat["spent"]["bonus"]:
                        raise CombatError("You already used your bonus action this turn.")
                    combat["spent"]["bonus"] = True
            label = {"action": "action", "bonus": "bonus action", "reaction": "reaction", "free": "no action"}.get(cost, cost)
            if option.get("grants") == "action":
                combat["extra_actions"] = combat.get("extra_actions", 0) + 1
            if kind in ("grapple", "shove"):
                target = self._get(combat, target_id)
                if target["hp"] <= 0:
                    raise CombatError(f"{target['name']} is already down.")
                combat["spent"]["attacked"] = True  # it replaces one attack of the Attack action
                line = self._contest(state, me, target, kind)
            elif kind == "opportunity":
                target = self._get(combat, target_id)
                reach = me.get("range", 1) if me.get("range", 1) <= 2 else 1  # melee only: a bow's range is not reach
                if distance(me["x"], me["y"], target["x"], target["y"]) > reach:
                    raise CombatError(f"{target['name']} is out of your reach: an opportunity attack hits someone leaving your reach.")
                line = self._attack(combat, me, target, "", head=f"**{me['name']} makes an opportunity attack on {target['name']} (reaction)**")
            elif option.get("cast"):
                line = self._cast(combat, me, target_id, name, option["cast"])
            elif kind == "smite":
                line = self._smite(combat, me, option["smite"])
            elif kind == "dash":
                combat["moved"] = combat.get("moved", 0) - me.get("speed", 6)
                line = f"**{me['name']} dashes** ({label})\n🏃 +{me.get('speed', 6) * 5} ft of movement this turn."
            else:
                line = f"**{me['name']} uses {name}** ({label})" + (f"\n{option['result']}" if option.get("result") else "")
                if kind == "disengage":
                    line += "\n🛡 Moving away provokes no opportunity attacks this turn."
        except CombatError:  # refused (no target, out of range, the caster inside the blast…): the action is not spent
            combat.update(kept)
            raise
        if option.get("hp") is not None:  # a feature that healed (Second Wind): the fight's HP follows the sheet
            me["hp"] = int(clamp(as_int(option["hp"], me["hp"]), 0, me["max_hp"]))
        combat["turn_lines"].append(line)
        combat["log"] = (combat.get("log", []) + [line])[-30:]
        self._sync_player(state)
        mine = self.current(combat)["side"] == "player"
        return state, line + ("\n\n" + self.turn_left(state) if mine else "")

    @staticmethod
    def describe_last(state: dict, text: str) -> dict:
        """Your own words for the part of the turn you just played ("Want to describe it?"): shown under its header in
        the round card. They change no rule and call no AI by themselves."""
        combat = state.get("combat") or {}
        lines = combat.get("turn_lines") or []
        if not combat.get("active") or not lines:
            raise CombatError("There is nothing of your turn to describe yet.")
        text = " ".join(str(text or "").split())[:400]
        if not text:
            return state
        head, _, rest = lines[-1].partition("\n")
        quoted = f'💬 "{text}"'
        lines[-1] = f"{head}\n{quoted}" + (f"\n{rest}" if rest else "")
        log = combat.get("log") or []
        if log and log[-1].partition("\n")[0] == head:
            log[-1] = lines[-1]
        return state

    def _flavour(self, c: dict, target: dict, block: str) -> str:
        """A line of colour before and after a companion's roll, from its weapon and the result (no AI, no wait)."""
        lines = block.split("\n")
        weapon = c.get("weapon") or ""
        name, foe = c["name"], target["name"]
        if c.get("range", 1) > 1:
            before = self.rng.choice([f"*{name} takes aim and looses a shot at {foe}{' with the ' + weapon if weapon else ''}.*",
                                      f"*{name} draws, breathes out, and fires at {foe}.*"])
        else:
            w = f" the {weapon}" if weapon else " a weapon"
            before = self.rng.choice([f"*{name} closes the distance and swings{w} at {foe}.*",
                                      f"*{name} steps in hard, bringing{w} down on {foe}.*",
                                      f"*{name} feints, then strikes at {foe} with{w}.*"])
        roll = next((x for x in lines if x.startswith("🎲")), "")
        m = re.search(r"= (-?\d+) vs AC (\d+)", roll)
        if "defeated" in block:
            after = self.rng.choice([f"*{foe} crumples to the ground.*", f"*{foe} goes down and stays down.*"])
        elif "CRITICAL" in roll:
            after = "*A brutal, perfect hit!*"
        elif "HIT" in roll:
            after = self.rng.choice(["*It lands!*", "*A solid hit.*", f"*{foe} staggers back.*"])
        elif m and int(m.group(2)) - int(m.group(1)) <= 2:
            after = "*So close: a near miss!*"
        else:
            after = self.rng.choice(["*The blow goes wide.*", f"*{foe} slips aside.*"])
        return "\n".join([lines[0], before, *lines[1:], after])

    def player_step(self, state: dict, action: str, target_id: str = "", advantage: str = "", ability_id: str = "") -> tuple[dict, str]:
        """One part of the player's turn (from the Combat tab's buttons): rolled at once, the turn goes on."""
        combat, me = self._check_my_turn(state)
        block = self._do(state, combat, me, action, target_id, advantage, ability_id)
        combat["turn_lines"].append(block)
        combat["log"] = (combat.get("log", []) + [block])[-30:]
        self._sync_player(state)
        if self._finished(combat):  # the fight is won: End turn sends it all to the Aedo, who tells the ending
            return state, block + "\n\n🏁 No enemy is left standing. End your turn to finish the fight."
        return state, block + "\n\n" + self.turn_left(state)

    def player_turn(self, state: dict, actions: list[str], target_id: str = "", advantage: str = "", bonus_target: str = "") -> tuple[dict, str]:
        """A typed message is the player's whole turn: each part it names is rolled, then the turn ends."""
        combat = state.get("combat") or {}
        if combat.get("active"):
            lines_before = self._others_until_player(combat)
            if lines_before:
                combat.setdefault("turn_lines", [])[:0] = lines_before
        for i, action in enumerate(actions):
            if self._finished(combat):
                break
            combat_, me = self._check_my_turn(state)
            try:
                tid = (bonus_target or target_id) if action == "bonus_attack" else target_id
                if tid and self._get(combat_, tid)["hp"] <= 0:  # the first blow already dropped it: the nearest one standing
                    tid = find_target(combat_, "")
                block = self._do(state, combat_, me, action, tid, advantage, "")
            except CombatError as exc:
                if i == 0:
                    raise
                block = f"✋ {exc}"
            combat_["turn_lines"].append(block)
        return self.player_action(state, "end")

    def player_action(self, state: dict, action: str, target_id: str = "", advantage: str = "", ability_id: str = "") -> tuple[dict, str]:
        """The player's action (or "end": just end the turn), then every other combatant until it is the player's turn
        again (one GM reply per round). Parts of the turn already played with player_step come first."""
        combat = state.get("combat") or {}
        if not combat.get("active"):
            raise CombatError("There is no fight going on.")
        me = next(c for c in combat["combatants"] if c["side"] == "player")
        round_no = combat["round"]
        lines: list[str] = []
        # Anyone before the player in the order acts first (start of the fight, or after a free text turn).
        lines += self._others_until_player(combat)
        if self._finished(combat):
            lines = list(combat.pop("turn_lines", []) or []) + lines
            combat["turn_lines"] = []
            self._sync_player(state)
            return self._wrap(state, lines, round_no)
        if action != "end":
            combat_, me = self._check_my_turn(state)
            lines.append(self._do(state, combat_, me, action, target_id, advantage, ability_id))
        lines = list(combat.get("turn_lines") or []) + lines
        combat["turn_lines"] = []
        if not self._finished(combat):
            self._advance(combat)
            lines += self._others_until_player(combat)
        self._sync_player(state)
        return self._wrap(state, lines, round_no)

    def _act(self, state: dict, combat: dict, me: dict, action: str, target_id: str, advantage: str, ability_id: str) -> str:
        lines: list[str] = []
        if action == "attack":
            target = self._get(combat, target_id)
            if target["hp"] <= 0:
                raise CombatError(f"{target['name']} is already down.")
            moved, in_reach = self._close_in(combat, me, target)
            if not in_reach:
                lines.append(f"**{me['name']} runs at {target['name']}**\n{moved}")
            else:
                block = self._attack(combat, me, target, advantage if advantage in ("advantage", "disadvantage") else "",
                                     head=f"**{me['name']} attacks {target['name']}" + (f" ({me['weapon']})" if me.get("weapon") else "") + "**")
                if moved:
                    head, _, rest = block.partition("\n")
                    block = f"{head}\n{moved}\n{rest}"
                lines.append(block)
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
        return "\n\n".join(lines)

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

    def _close_in(self, combat: dict, me: dict, target: dict) -> tuple[str, bool]:
        """Out of reach: the player walks toward the target with the movement left this turn. Still too far: they Dash
        (double move, no attack this turn). Returns (the move line, whether the target is now in reach)."""
        reach = me.get("range", 1)
        if distance(me["x"], me["y"], target["x"], target["y"]) <= reach:
            return "", True
        left = max(0, me.get("speed", 6) - combat.get("moved", 0))
        occupied = {(o["x"], o["y"]) for o in combat["combatants"] if o["hp"] > 0 and o["id"] != me["id"]}
        g = combat["grid"]
        tiles = g.get("tiles") or []
        nx, ny = path_step(tiles, (me["x"], me["y"]), (target["x"], target["y"]), occupied, left, (g["w"], g["h"])) if left else (me["x"], me["y"])
        dash = distance(nx, ny, target["x"], target["y"]) > reach
        if dash:  # the Dash action: the whole turn spent running toward it
            nx, ny = path_step(tiles, (me["x"], me["y"]), (target["x"], target["y"]), occupied, left + me.get("speed", 6), (g["w"], g["h"]))
        budget = left + (me.get("speed", 6) if dash else 0)
        steps = walk_cost(tiles, (me["x"], me["y"]), (nx, ny), occupied, budget, (g["w"], g["h"])) or distance(me["x"], me["y"], nx, ny)
        me["x"], me["y"] = nx, ny
        combat["moved"] = combat.get("moved", 0) + steps
        if dash:
            return (f"🏃 {me['name']} dashes {steps} squares ({steps * 5} ft) toward {target['name']}, "
                    f"still out of reach: no attack this turn."), False
        return f"🏃 {me['name']} moves {steps} squares ({steps * 5} ft) toward {target['name']}.", True

    def move_player(self, state: dict, x: int, y: int) -> dict:
        """The player walks on the map, on their own turn only, up to their speed (difficult ground costs double)."""
        combat = state.get("combat") or {}
        if not combat.get("active"):
            raise CombatError("There is no fight going on.")
        me = next(c for c in combat["combatants"] if c["side"] == "player")
        if self.current(combat)["id"] != me["id"]:
            raise CombatError(f"It is {self.current(combat)['name']}'s turn. You can move on your turn.")
        if me["hp"] <= 0:
            raise CombatError("You are unconscious.")
        g = combat["grid"]
        gx, gy = as_int(x, me["x"]), as_int(y, me["y"])
        left = max(0, me.get("speed", 6) - combat.get("moved", 0))
        occupied = {(o["x"], o["y"]) for o in combat["combatants"] if o["hp"] > 0 and o["id"] != me["id"]}
        cost = walk_cost(g.get("tiles") or [], (me["x"], me["y"]), (gx, gy), occupied, left, (g["w"], g["h"]))
        if cost is None:
            if not (0 <= gx < g["w"] and 0 <= gy < g["h"]) or blocked(g.get("tiles") or [], gx, gy) or (gx, gy) in occupied:
                raise CombatError("You cannot stand there.")
            raise CombatError(f"Too far: you can move {left} more squares ({left * 5} ft) this turn.")
        me["x"], me["y"] = gx, gy
        combat["moved"] = combat.get("moved", 0) + cost
        return state

    @staticmethod
    def use_reaction(state: dict) -> None:
        """A check during a fight (a reaction, helping someone, looking around) is one per round."""
        combat = state.get("combat") or {}
        if not combat.get("active"):
            return
        if combat.get("reaction_round") == combat["round"]:
            raise CombatError("You already made a check this round (one reaction per round). It comes back next round.")
        combat["reaction_round"] = combat["round"]

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
                if c.get("dying"):  # down: the turn is a death saving throw, rolled by the app (one per round)
                    lines.append(self._death_save(combat, c))
                    if c["hp"] > 0:
                        break  # a natural 20: back up, and it is their turn
                    self._advance(combat)
                    break
                self._advance(combat)
                continue
            if c["hp"] <= 0:
                self._advance(combat)
                continue
            healed = self._companion_heal(combat, c) if c.get("companion") else ""
            if healed:
                lines.append(healed)
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
                                       occupied, c.get("speed", 6), (combat["grid"]["w"], combat["grid"]["h"]))
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
                    if c.get("companion"):
                        block = self._flavour(c, target, block)
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
        text = f"⚔️ **Round {round_no}**\n\n" + "\n\n".join(self._by_turns(combat, lines))
        me = me_down(combat)
        if done == "you have fallen":
            if me.get("dying"):
                text += "\n\n" + self._fall_out(combat, me)
            self._sync_player(state)
        elif done and me["hp"] <= 0 and not me.get("dead"):  # won while down: the companions see to the player
            me.update(hp=1, dying=False, stable=True)
            text += f"\n\n🩹 The companions stabilize {me['name']}, who comes to with 1 HP."
            self._sync_player(state)
        if done:
            state, end_line = self.end(state, done)
            text += "\n\n🏁 " + end_line.replace("⚔️ ", "")
        combat["log"] = (combat.get("log", []) + lines)[-30:]
        return state, text

    @staticmethod
    def _by_turns(combat: dict, lines: list[str]) -> list[str]:
        """The round told turn by turn: a "**Name's turn**" heading whenever the one acting changes. A companion's
        first turn in the fight also gets "[[face: Name]]": the round card shows their picture there."""
        names = sorted((c["name"] for c in combat["combatants"]), key=len, reverse=True)
        allies = {c["name"] for c in combat["combatants"] if c.get("side") == "ally"}
        faced = combat.setdefault("faced", [])
        out, current = [], None
        for line in lines:
            who = next((n for n in names if line.startswith(f"**{n} ") or line.startswith(f"**{n}**")), None)
            if who and who != current:
                out.append(f"**{who}'s turn**")
                if who in allies and who not in faced:
                    out.append(f"[[face: {who}]]")
                    faced.append(who)
                current = who
            out.append(line)
        return out

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
    "The player's own words before the ⚔️ block say HOW they attack: narrate the verified result in that style (a hit "
    "that defeats the enemy can be the clean cut they described; a miss stays a miss). Never roll dice, never write "
    "attack rolls or damage numbers and never decide a hit yourself: if the player's message has no ⚔️ block, nothing "
    "was rolled, so do not resolve any attack; describe the moment and ask what they do. Enemy attacks are rolled by the "
    "app against the player's AC, so never ask the player for a roll to dodge or resist them. Ask for at most one check "
    "per round (a reaction, helping an ally, spotting something), always with its DC. "
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


# ------------------------------------------------------------------ attacks typed in the chat
ATTACK_WORDS = re.compile(
    r"\b(attack\w*|strik\w*|swing\w*|slash\w*|stab\w*|cut\w*|hit|hits|shoot\w*|lunge\w*|thrust\w*|smash\w*|bash\w*|"
    r"punch\w*|kick\w*|behead\w*|decapitat\w*|cleav\w*|chop\w*|skewer\w*|impal\w*|fire\w* at|throw\w* (?:my |an? |the )?"
    r"(?:axe|handaxe|dagger|javelin|spear)\w*|"
    r"atac\w*|ataque\w*|golpe\w*|golpei\w*|cort\w*|esfaque\w*|acert\w*|atir\w*|dispar\w*|decapit\w*|soc\w*|chut\w*|"
    r"perfur\w*|empal\w*|arremess\w*)\b", re.I)
COMMAND = re.compile(r"^\s*/(attack|atacar|atk|dodge|esquivar)\b[ \t]*(.*)$", re.I | re.S)
SPOKEN = re.compile(r"\"[^\"]*\"|“[^”]*”|(?<!\w)'[^'\n]+'(?!\w)")  # speech and thoughts are not actions


def _base(name: str) -> str:
    return re.sub(r"\s*#?\d+$", "", name).strip().lower()


NUMBERS = {w: i for i, ws in enumerate([[], ["one", "um", "uma"], ["two", "dois", "duas"], ["three", "três", "tres"], ["four", "quatro"],
                                         ["five", "cinco"], ["six", "seis"], ["seven", "sete"], ["eight", "oito"]]) for w in ws}
NUMBER_WORDS = re.compile(r"\b(" + "|".join(sorted(NUMBERS, key=len, reverse=True)) + r")\b", re.I)


def find_target(combat: dict, text: str) -> str:
    """The enemy the text names ("Goblin 3", "goblin #3", "the goblin", "the bugbear"), else the nearest one."""
    me = next((c for c in combat["combatants"] if c["side"] == "player"), None)
    alive = [c for c in combat["combatants"] if c["side"] == "enemy" and c["hp"] > 0]
    if not alive:
        return ""
    low = NUMBER_WORDS.sub(lambda m: str(NUMBERS[m.group(0).lower()]), (text or "").lower())  # "goblin one" = Goblin 1
    near = (lambda c: distance(me["x"], me["y"], c["x"], c["y"])) if me else (lambda c: 0)
    for c in alive:  # a numbered name first
        num = re.search(r"(\d+)$", c["name"])
        pat = re.escape(_base(c["name"])) + (rf"s?\s*#?\s*{num.group(1)}\b" if num else r"\b")
        if re.search(rf"\b{pat}", low):
            return c["id"]
    named = [c for c in alive if re.search(rf"\b{re.escape(_base(c['name']))}(s|es)?\b", low)]
    return min(named or alive, key=near)["id"]


BONUS_WORDS = re.compile(r"\b(bonus action|martial arts|flurry|a[çc][ãa]o b[ôo]nus|artes marciais|rajada)\b", re.I)
END_WORDS = re.compile(r"^\s*/(end|fim|pass|passar)\b|\b(end (my|the) turn|i end|finish my turn|passo (o|a) (vez|turno)|encerro (o|meu) turno)\b", re.I)


def split_turn(text: str) -> tuple[str, str]:
    """(the action's words, the bonus action's words): "...the goblin one with my action, and with my bonus action the goblin 2"."""
    t = text or ""
    m = re.search(r"(,?\s*(and|then|e|depois)?\s*(with|using|use|com|usando)?\s*(my|a|minha)?\s*)?(bonus action|a[çc][ãa]o b[ôo]nus|martial arts|artes marciais|flurry)", t, re.I)
    if not m:
        return t, ""
    return t[:m.start()].strip(" ,"), t[m.start():].strip(" ,")


def bonus_intent(text: str) -> bool:
    """The typed turn also uses a bonus action (a Monk's Martial Arts strike, Flurry of Blows)."""
    return bool(BONUS_WORDS.search(SPOKEN.sub(" ", text or "")))


def end_intent(text: str) -> bool:
    return bool(END_WORDS.search(text or ""))


def combat_intent(combat: dict, text: str) -> tuple[str, str, str] | None:
    """A message typed during a fight that is an attack: (move, target id, the player's words).
    /attack [enemy] [how] and /dodge [how] always count; otherwise an attack word in the text does."""
    if not (combat or {}).get("active") or not (text or "").strip():
        return None
    if not any(c["side"] == "enemy" and c["hp"] > 0 for c in combat["combatants"]):
        return None
    m = COMMAND.match(text)
    if m:
        cmd, rest = m.group(1).lower(), m.group(2).strip()
        if cmd in ("dodge", "esquivar"):
            return "dodge", "", rest
        return "attack", find_target(combat, rest), rest
    t = text.strip()
    if t.startswith(("/", "(", "[", "OOC", "ooc")) or t.endswith("?") or not ATTACK_WORDS.search(SPOKEN.sub(" ", t)):
        return None
    return "attack", find_target(combat, t), t
