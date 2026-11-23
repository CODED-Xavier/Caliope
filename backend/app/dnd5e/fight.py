"""The 5e sheet inside a fight: features with uses, spells that spend a slot and roll, Divine Smite after a hit, and
the reactions the app takes for you on enemy turns (Shield, Uncanny Dodge). The web server only calls these."""
from ..combat import CombatError
from . import actions, magic, store
from .character import derive


def settle_auto(state: dict, lib) -> None:
    """Slots the automatic reactions spent on enemy turns (🛡 Shield) come off the sheet."""
    combat, char = state.get("combat") or {}, state.get("character5e")
    spent = [x for x in combat.get("auto_spent", []) if x == "slot"]
    if not char or not spent:
        return
    for _ in spent:
        try:
            char, _lv = magic.spend_slot(char, derive(char, lib), 1)
        except ValueError:
            break
    combat["auto_spent"] = []
    store.put_char(state, "", char, lib)
    auto_reactions(state, lib)


def auto_reactions(state: dict, lib) -> None:
    """Which reactions the app may take for you on enemy turns: Shield (on your sheet, with a slot) and Uncanny Dodge."""
    combat, char = state.get("combat") or {}, state.get("character5e")
    if not combat.get("active") or not char:
        return
    sheet = derive(char, lib)
    auto = combat.setdefault("auto_reactions", {})
    has_shield = any(sp.get("name", "").lower() == "shield" for sp in char.get("spells") or [])
    auto["slots"] = sum(sheet.get("slots_left", {}).values()) + sheet.get("pact_left", 0) if has_shield else 0
    auto.setdefault("shield", has_shield)
    if not has_shield:
        auto["shield"] = False
    uncanny = any(f["name"] == "Uncanny Dodge" for f in sheet["features"])
    auto.setdefault("uncanny", uncanny)
    if not uncanny:
        auto["uncanny"] = False
    auto["can"] = [k for k, ok in (("shield", has_shield), ("uncanny", uncanny)) if ok]


def cast_in_fight(engine, state: dict, lib, option_id: str, target: str, advantage: str, slot: int | None = None,
                   amount: int | None = None):
    """An option from the 5e list in a fight: features with uses, spells (slot spent, attack or saves rolled, damage
    or healing applied, areas hit everyone inside) and Divine Smite after a hit."""
    char = state.get("character5e")
    if not char:
        raise CombatError("The action list needs a 5e sheet.")
    option = actions.find(char, lib, option_id)
    if not option:
        raise CombatError("That is not one of your options.")
    me = next((c for c in (state.get("combat") or {}).get("combatants", []) if c["side"] == "player"), None)
    try:
        if option["kind"] == "feature" and "uses_left" in option:
            if option["uses_left"] <= 0:
                raise CombatError(f"{option['name']} is used up until you rest.")
            store.pull_hp(state, "")
            char, result = store.use_feature(char, option["name"], lib, amount=amount)
            store.put_char(state, "", char, lib)
            option = {**option, "result": result, "hp": state["player"]["hp"]["current"]}
            if option["name"] == "Rage" and me is not None:  # raging until the fight ends
                me["raging"] = True
                me["rage_bonus"] = magic.rage_bonus(derive(char, lib)["level"])
        elif option["kind"] == "spell":
            e = lib.items.get(("spell", option["name"].lower(), next((sp.get("source", "PHB") for sp in char.get("spells") or []
                                                                      if sp["name"].lower() == option["name"].lower()), "PHB").upper()))
            sheet = derive(char, lib)
            used = 0
            if int(option.get("level") or 0) > 0:
                char, used = magic.spend_slot(char, sheet, int(option["level"]), slot)
                store.put_char(state, "", char, lib)
            ab = sheet.get("spell_ability") or "int"
            roll = magic.spell_roll(e or {}, sheet["level"], used or int(option.get("level") or 0), sheet["abilities"][ab]["mod"])
            option = {**option, "cast": {**roll, "slot": used, "dc": sheet.get("spell_dc", 10), "attack": sheet.get("spell_attack", 2),
                                         "area": option.get("area")}}
        elif option["kind"] == "smite":
            last = (state.get("combat") or {}).get("last_hit")
            if not last or not last.get("melee"):
                raise CombatError("Divine Smite comes right after you hit with a melee weapon.")
            sheet = derive(char, lib)
            char, used = magic.spend_slot(char, sheet, 1, slot)
            store.put_char(state, "", char, lib)
            foe = next((c for c in state["combat"]["combatants"] if c["id"] == last["target"]), {})
            option = {**option, "smite": {"slot": used, "dice": magic.smite_dice(used, foe.get("name", ""))}}
    except ValueError as exc:
        raise CombatError(str(exc)) from exc
    state, line = engine.use_option(state, option, target, advantage)
    auto_reactions(state, lib)
    return state, line
