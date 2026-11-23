"""FastAPI app. Run with:  python run.py   (API docs at http://localhost:8000/docs)"""
from __future__ import annotations

import asyncio
import json
import os
import re
import logging
from contextlib import aclosing, asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from .cardio import export_card, parse_card
from .cards import resolve_features
from .config import APP_HOME, DB_PATH, FRONTEND_DIST
from .conversations import NotFound
from .drafts import draft_card_field, draft_player
from .exporting import export_markdown
from .combat import AreaRisk, CombatError, bonus_intent, combat_intent, end_intent, find_target, player_defaults, split_turn, suggest_fight
from .combat import _picture_geometry as combat_geometry
from .dnd5e import fight as fight5e
from .maps import FEATURES as MAP_FEATURES
from .maps import TILES as MAP_TILES
from .maps import TYPES as MAP_TYPES
from .maps import MapError, generate as generate_map
from .maps import clean_tiles as clean_map_tiles
from .jukebox import MOODS as MUSIC_MOODS
from .jukebox import MusicError
from .rulebooks import RulebookError, ocr_available, read_pdf, read_text
from .runtime import ENGINE_KEYS, EngineError
from .runtime import server_binary as runtime_binary
from .modelhub import adopt_models, download_root, pick_model_file, use_own_models
from .picker import pick_folder
from . import backups, cardpics, hardware, npcfill, r2
from . import writing_help
from .voice import CATALOG as VOICE_CATALOG, VoiceError
from .images import UPLOAD_NAME, ImageError, get_image, http_fetch, save_upload
from .scenes import PixAIError, is_pixai, is_pollinations, pixai_paint, polite_fetch
from .playerlore import parse_suggestions, suggest_prompt
from .checks import roll_line
from . import shop
from . import resources
from . import adventure, bestiary, mappaint, party, sheets, statusbook, wikiresearch
from . import systems, worldtime
from .engine import BusyError
from .llm import LLMError
from .scenarios import generate_scenario, normalize_scenario
from .services import Services
from .skills import SkillError
from .state import normalize_state
from .util import as_int, deep_merge

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.svc = Services()
    app.state.tasks = set()
    use_own_models(app.state.svc.settings)
    background(asyncio.to_thread(adopt_models, app.state.svc.settings))  # LM Studio's copies move into Calíope's folder
    if app.state.svc.settings.get("ai_engine") == "builtin":
        background(app.state.svc.runtime.start())  # the app opens at once; the model loads behind it
    background(catch_up_embeddings())
    background(daily_backups())
    yield
    await app.state.svc.close()


async def daily_backups() -> None:
    """A copy of every game once a day (the first time the app runs that day, and on long sessions past midnight)."""
    while True:
        s = svc()
        if s.settings.get("backups"):
            try:
                made = await asyncio.to_thread(backups.backup_now, s.db.conn, s.db._lock, s.db.path, int(s.settings.get("backups_keep") or 7))
                if made:
                    logging.getLogger("rpg").info("Backup saved: %s", made["name"])
            except Exception as exc:  # never stop the app over a backup
                logging.getLogger("rpg").warning("Backup failed: %s", exc)
        await asyncio.sleep(3600)


async def catch_up_embeddings() -> None:
    """Memories and rulebooks saved before an embedding model was chosen (or with another one) get vectors for
    the current model, so search by meaning covers everything. Waits for the model server to answer first."""
    s = svc()
    from .config import embedding_key
    if not embedding_key(s.settings.all()):
        return
    for _ in range(60):  # up to 5 minutes (the built-in engine may still be loading)
        if await s.llm.embed(["ready?"]):
            break
        await asyncio.sleep(5)
    else:
        return
    try:
        mem = await s.memory.reindex()
        books = await s.rulebooks.embed_missing()
        if mem or books:
            logging.getLogger("rpg").info("Embedded %s memories and %s rulebook passages for the current model", mem, books)
    except Exception as exc:  # optional: keyword search keeps working
        logging.getLogger("rpg").warning("Catching up embeddings failed: %s", exc)


def background(coro) -> None:
    """Run a coroutine without waiting for it (kept referenced so it is not garbage-collected mid-way)."""
    task = asyncio.create_task(coro)
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)


app = FastAPI(title="Calíope", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def _host_of(value: str) -> str:
    value = (value or "").strip().lower()
    if value.startswith("["):
        return value.split("]")[0] + "]"
    return value.split(":")[0]


@app.middleware("http")
async def local_only(request: Request, call_next):
    """The app is only for this PC. Refuse requests that name another host (a web page that points its own
    domain at 127.0.0.1, "DNS rebinding"), and changes sent by other web sites open in the browser."""
    if _host_of(request.headers.get("host", "")) not in _LOCAL_HOSTS:
        return JSONResponse({"detail": "Calíope only answers on this PC (127.0.0.1)."}, status_code=403)
    origin = request.headers.get("origin")
    if origin and request.method not in ("GET", "HEAD", "OPTIONS"):
        from urllib.parse import urlparse
        if _host_of(urlparse(origin).netloc) not in _LOCAL_HOSTS:
            return JSONResponse({"detail": "Requests from other web sites are not allowed."}, status_code=403)
    return await call_next(request)


def svc() -> Services:
    return app.state.svc


@app.exception_handler(NotFound)
async def _not_found(_: Request, exc: NotFound):
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(VoiceError)
async def _voice_error(_: Request, exc: VoiceError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(ValueError)  # also covers DiceError and SkillError
async def _bad_request(_: Request, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(BusyError)
async def _busy(_: Request, exc: BusyError):
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(LLMError)
async def _llm_error(_: Request, exc: LLMError):
    return JSONResponse({"detail": str(exc)}, status_code=502)


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def stream_response(events: AsyncIterator[dict]) -> StreamingResponse:
    async def gen():
        try:
            async with aclosing(events) as stream:
                async for event in stream:
                    yield sse(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # never leave the browser hanging
            logging.exception("Turn failed")
            yield sse({"type": "error", "message": f"Unexpected error: {exc}"})

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ------------------------------------------------------------------ health/models
@app.get("/api/health")
async def health():
    return {"backend": "ok", "llm": await svc().llm.health(), "skills": len(svc().skills.list()),
            "engine": svc().runtime.status(with_log=False)}


@app.get("/api/models")
async def models():
    return {"models": await svc().llm.list_models()}


# ----------------------------------------------------------------------- settings
@app.get("/api/settings")
async def get_settings():
    return svc().settings.all()


@app.put("/api/settings")
async def put_settings(values: dict[str, Any] = Body(...)):
    return apply_settings(values)


def apply_settings(values: dict) -> dict:
    """Save settings; reload or stop the built-in engine when one of its settings changed."""
    from .config import embedding_key
    before = svc().settings.all()
    after = svc().settings.update(values)
    if embedding_key(after) and embedding_key(after) != embedding_key(before):
        background(catch_up_embeddings())
    if any(before.get(k) != after.get(k) for k in ENGINE_KEYS):  # model, port, context... changed: reload the engine
        if after.get("ai_engine") == "builtin":
            background(svc().runtime.start())
        elif before.get("ai_engine") == "builtin":
            background(svc().runtime.stop())
    return after


@app.post("/api/settings/reset")
async def reset_settings():
    return svc().settings.reset()


# --------------------------------------------------------------------- scenarios
@app.get("/api/scenarios")
async def list_scenarios():
    return svc().scenarios.list()


@app.post("/api/scenarios/generate")
async def generate(body: dict[str, Any] = Body(...)):
    idea = str(body.get("idea", "")).strip()
    if not idea:
        raise ValueError("Describe the scenario idea.")
    data = await generate_scenario(svc().llm, idea, body.get("mode", "gm_world"), body.get("language", "en"), body.get("kind"))
    return {"data": data}  # not saved yet: edit it, then POST /api/scenarios


@app.post("/api/scenarios")
async def create_scenario(data: dict[str, Any] = Body(...)):
    return svc().scenarios.create(data)


@app.get("/api/scenarios/{scenario_id}")
async def get_scenario(scenario_id: int):
    scenario = svc().scenarios.get(scenario_id)
    if not scenario:
        raise NotFound(f"Scenario {scenario_id} not found")
    return scenario


@app.get("/api/scenarios/{scenario_id}/start-sheet")
async def scenario_start_sheet(scenario_id: int):
    """The card's own sheet (Tier, Attributes, Stats with EXP...) to fill on the start screen."""
    scenario = svc().scenarios.get(scenario_id)
    if not scenario:
        raise NotFound(f"Scenario {scenario_id} not found")
    return statusbook.start_sheet(scenario["data"])


@app.post("/api/scenarios/{scenario_id}/companions")
async def save_companions(scenario_id: int, body: dict[str, Any] = Body(...)):
    """"Keep them on the card": the start screen's companion setup (names, looks, pictures) saved into the card."""
    from .party import apply_companion_edits
    scenario = svc().scenarios.get(scenario_id)
    if not scenario:
        raise NotFound(f"Scenario {scenario_id} not found")
    data = {**scenario["data"], "name": scenario["name"]}
    data["npcs"] = apply_companion_edits(data.get("npcs") or [], body.get("companions"))
    return svc().scenarios.update(scenario_id, data)


@app.post("/api/scenarios/{scenario_id}/systems/find")
async def find_systems(scenario_id: int):
    """🔍 Find systems: the card's own sheet proposed from its text (catalog parsed, the rest read by the AI)."""
    scenario = svc().scenarios.get(scenario_id)
    if not scenario:
        raise NotFound(f"Scenario {scenario_id} not found")
    return {"systems": await systems.read_card(svc().llm, scenario["data"])}


@app.post("/api/scenarios/{scenario_id}/systems/try")
async def try_systems(scenario_id: int, body: dict[str, Any] = Body(default={})):
    """The start screen: the sheet as you set it, checked by the card's rules, with the numbers worked out."""
    scenario = svc().scenarios.get(scenario_id)
    if not scenario:
        raise NotFound(f"Scenario {scenario_id} not found")
    sys_def = scenario["data"].get("systems") or {}
    st = systems.merge_state(sys_def, body.get("state"))
    error = systems.set_part(sys_def, st, str(body["slot"]), str(body.get("item") or "")) if body.get("slot") else ""
    return {"state": st, "computed": systems.compute(sys_def, st), "error": error}


@app.put("/api/scenarios/{scenario_id}")
async def update_scenario(scenario_id: int, data: dict[str, Any] = Body(...)):
    before = svc().scenarios.get(scenario_id)
    scenario = svc().scenarios.update(scenario_id, data)
    if not scenario:
        raise NotFound(f"Scenario {scenario_id} not found")
    svc().conversations.sync_card_portraits(scenario_id, (before or {}).get("data", {}).get("npcs", []), scenario["data"].get("npcs", []))
    return scenario


_LIBRARY: dict = {}


def library5e():
    """The 5e library (SRD built in + the user's files in data/compendium/dnd5e), loaded on first use."""
    from .dnd5e.library import default_library
    if "lib" not in _LIBRARY:
        lib = default_library(Path(DB_PATH).parent)
        lib.load()
        _LIBRARY["lib"] = lib
    return _LIBRARY["lib"]


@app.get("/api/library/5e")
async def library_search(type: str = Query("spell"), q: str = Query(""), edition: str = Query("2014"), limit: int = Query(60), category: str = Query(""),
                         hidden: bool = Query(False), cls: str = Query(""), max_level: int = Query(-1)):
    lib = await asyncio.to_thread(library5e)
    return {"results": lib.search(type, q, "2024" if edition == "2024" else "2014", max(1, min(500, limit)), category, include_hidden=hidden,
                                  cls=cls, max_level=None if max_level < 0 else max_level)}


@app.get("/api/library/5e/choices")
async def library_choices():
    """Your Library choices: hidden entries (kind|name|source) and the rules list of each book (2014, 2024 or both)."""
    lib = await asyncio.to_thread(library5e)
    return {**lib.choices, "books": lib.info.get("books", [])}


@app.put("/api/library/5e/choices")
async def library_save_choices(body: dict[str, Any] = Body(...)):
    lib = await asyncio.to_thread(library5e)
    return {**await asyncio.to_thread(lib.save_choices, body), "books": lib.info.get("books", [])}


@app.get("/api/library/5e/details")
async def library_details(type: str = Query(...), source: str = Query(...), name: str = Query(...)):
    """What a class gives at each level, a race's traits, a background's skills, equipment and feature."""
    from .dnd5e import details
    return details.describe(await asyncio.to_thread(library5e), type, name, source)


@app.get("/api/library/5e/entry")
async def library_entry(type: str = Query(...), source: str = Query(...), name: str = Query(...)):
    got = (await asyncio.to_thread(library5e)).get(type, source, name)
    if not got:
        raise NotFound("That entry is not in the library.")
    return got


@app.get("/api/library/5e/status")
async def library_status():
    lib = await asyncio.to_thread(library5e)
    return {**lib.info, "folder": str(Path(DB_PATH).parent / "compendium" / "dnd5e")}


@app.post("/api/library/5e/reload")
async def library_reload():
    _LIBRARY.pop("lib", None)
    return await library_status()


def _sheet_reply(state: dict, who: str = "") -> dict:
    from .dnd5e.character import derive
    from .dnd5e.store import char_of
    char = char_of(state, who)
    return {"character": char, "sheet": derive(char, library5e()) if char else None, "player": state.get("player"),
            "who": who, "party": state.get("party"), "party5e_sheet": state.get("party5e_sheet")}


def _edition(s, conv_id: int) -> str:
    return "2024" if s.conversations.get(conv_id)["scenario"].get("system") == "dnd5e-2024" else "2014"


def _check_who(s, conv_id: int, state: dict, who: str) -> None:
    if who and who not in (state.get("party") or {}):
        raise ValueError(f"{who} is not in your party.")


@app.get("/api/conversations/{conv_id}/character")
async def get_character(conv_id: int, who: str = Query("")):
    s = svc()
    s.conversations.get(conv_id)
    from .dnd5e.store import pull_hp
    state = s.conversations.get_state(conv_id)
    pull_hp(state, who)
    return await asyncio.to_thread(_sheet_reply, state, who)


@app.patch("/api/conversations/{conv_id}/character")
async def change_character(conv_id: int, body: dict[str, Any] = Body(...), who: str = Query("")):
    """Add from the Library (drag and drop), remove, equip, pick, set: the numbers are worked out again.
    who = a companion's name changes that companion's sheet."""
    from .dnd5e import store
    from .dnd5e.character import new_character
    s = svc()
    s.conversations.get(conv_id)
    not_busy(conv_id)
    state = s.conversations.get_state(conv_id)
    _check_who(s, conv_id, state, who)
    lib = await asyncio.to_thread(library5e)
    store.pull_hp(state, who)
    base = store.char_of(state, who) or new_character(_edition(s, conv_id))
    store.put_char(state, who, store.apply_change(base, body.get("change") or {}, lib), lib)
    s.conversations.save_state(conv_id, state)
    return _sheet_reply(state, who)


@app.get("/api/conversations/{conv_id}/character/builder")
async def character_builder(conv_id: int, who: str = Query("")):
    from .dnd5e import build, store
    from .dnd5e.character import new_character
    s = svc()
    char = store.char_of(s.conversations.get_state(conv_id), who) or new_character(_edition(s, conv_id))
    return {"steps": await asyncio.to_thread(build.builder_steps, char, library5e()), "methods": build.ABILITY_METHODS}


@app.get("/api/conversations/{conv_id}/character/starting")
async def character_starting(conv_id: int, who: str = Query("")):
    """The class's and background's starting gear to choose from (or the class's gold instead), and your money."""
    from .dnd5e import equipment, store
    from .dnd5e.character import new_character
    s = svc()
    char = store.char_of(s.conversations.get_state(conv_id), who) or new_character(_edition(s, conv_id))
    return await asyncio.to_thread(equipment.starting_options, library5e(), char)


@app.get("/api/conversations/{conv_id}/character/levelup")
async def character_levelup_plan(conv_id: int, who: str = Query("")):
    from .dnd5e import build, store
    char = store.char_of(svc().conversations.get_state(conv_id), who)
    if not char:
        raise ValueError("This sheet is not a 5e sheet yet.")
    return await asyncio.to_thread(build.level_up_plan, char, library5e())


@app.get("/api/conversations/{conv_id}/character/levels")
async def character_levels(conv_id: int, who: str = Query("")):
    """📜 The 20 levels of this character's class: features, proficiency, slots, the class's columns, spells and uses."""
    from .dnd5e import levels, store
    char = store.char_of(svc().conversations.get_state(conv_id), who)
    if not char:
        raise ValueError("This sheet is not a 5e sheet yet.")
    return await asyncio.to_thread(levels.progression, char, library5e())


@app.post("/api/conversations/{conv_id}/character/levelup")
async def character_levelup(conv_id: int, body: dict[str, Any] = Body(...), who: str = Query("")):
    """Level up: HP (average or a roll), the class table's new features, and the player's choices."""
    from .dnd5e import build, store
    s = svc()
    not_busy(conv_id)
    state = s.conversations.get_state(conv_id)
    store.pull_hp(state, who)
    char = store.char_of(state, who)
    if not char:
        raise ValueError("This sheet is not a 5e sheet yet.")
    lib = await asyncio.to_thread(library5e)
    store.put_char(state, who, build.apply_level_up(char, body.get("answers") or {}, lib), lib)
    s.conversations.save_state(conv_id, state)
    return _sheet_reply(state, who)


@app.post("/api/conversations/{conv_id}/character/convert")
async def character_convert(conv_id: int):
    """Turn a game's free-form sheet into a 5e sheet: class, race, background and items matched in the Library."""
    from .dnd5e import store
    s = svc()
    not_busy(conv_id)
    state = s.conversations.get_state(conv_id)
    lib = await asyncio.to_thread(library5e)
    store.put_char(state, "", store.convert(state, lib, _edition(s, conv_id)), lib)
    s.conversations.save_state(conv_id, state)
    return _sheet_reply(state)


@app.post("/api/conversations/{conv_id}/character/party/auto")
async def character_party_auto(conv_id: int, body: dict[str, Any] = Body(default={})):
    """The system builds the companions' 5e sheets around the hero (front-liner, healer, spellcaster, support).
    name = only that companion; otherwise every companion still without a sheet (or all, with "all": true)."""
    from . import party
    from .dnd5e import party5e, store
    s = svc()
    not_busy(conv_id)
    conv = s.conversations.get(conv_id)
    state = s.conversations.get_state(conv_id)
    if state.get("party_mode") != "companions":
        raise ValueError("This game is played solo.")
    hero = state.get("character5e")
    if not hero or not hero.get("cls"):
        raise ValueError("Build your own hero first: the companions are chosen around your class.")
    lib = await asyncio.to_thread(library5e)
    only = str(body.get("name") or "")
    comps = [c for c in party.companions(conv["scenario"]) if c["name"] in (state.get("party") or {})]
    keep = {} if body.get("all") else {c["name"]: store.char_of(state, c["name"]) for c in comps}
    for name, char in party5e.auto_build_all(comps, hero, lib, only=only, keep=keep).items():
        store.put_char(state, name, char, lib)
    s.conversations.save_state(conv_id, state)
    return _sheet_reply(state)


@app.post("/api/conversations/{conv_id}/character/use")
async def use_character_feature(conv_id: int, body: dict[str, Any] = Body(...)):
    """A feature with uses (Second Wind, Action Surge, Rage…): spent, applied, and told to the Aedo."""
    from .dnd5e import store
    s = svc()
    s.conversations.get(conv_id)
    lib = await asyncio.to_thread(library5e)

    def prepare(st):
        if not st.get("character5e"):
            raise ValueError("This game has no 5e sheet.")
        store.pull_hp(st, "")
        st["character5e"], line = store.use_feature(st["character5e"], str(body.get("name", "")), lib,
                                                    amount=as_int(body.get("amount"), 0) or None)  # points from a pool (Lay on Hands, Ki)
        store.sync_player(st, lib)
        return st, line

    return stream_response(s.engine.send(conv_id, "", prepare=prepare))


@app.post("/api/scenarios/{scenario_id}/companions/draft")
async def draft_companions(scenario_id: int):
    """✨ Write companions: 3 new characters who fit the card, with fight sheets (you edit them before saving)."""
    card = svc().scenarios.get(scenario_id)
    if not card:
        raise NotFound(f"Scenario {scenario_id} not found")
    got = await party.draft(svc().llm, {**card["data"], "name": card["name"]})
    if not got:
        raise ValueError("The model did not write usable companions. Try again.")
    return {"companions": got}


@app.delete("/api/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: int):
    if not svc().scenarios.delete(scenario_id):
        raise NotFound(f"Scenario {scenario_id} not found")
    return {"deleted": True}


# ------------------------------------------------------------------ combat
@app.get("/api/conversations/{conv_id}/combat/defaults")
async def combat_defaults(conv_id: int, system: str = Query("d20")):
    """The player's fight numbers taken from the sheet (the start form shows them so you can change them)."""
    return player_defaults(svc().conversations.get_state(conv_id), system)


@app.post("/api/conversations/{conv_id}/combat/suggest")
async def combat_suggest(conv_id: int, body: dict[str, Any] = Body(default={})):
    """The AI reads the last messages and proposes the enemies (you confirm them in the form)."""
    s = svc()
    system = body.get("system", "d20")
    adv = s.conversations.get(conv_id)["scenario"].get("adventure") or {}
    state = s.conversations.get_state(conv_id)
    scene_foes = adventure.combat_enemies(adv, state)
    if scene_foes and system == "d20":  # the adventure says who is here: no need to ask the model
        battle = adventure.battle_map(adv, state)
        if battle is None and adventure.get_scene(adv, (state.get("adventure") or {}).get("scene", "")):
            battle = (await asyncio.to_thread(_paint_scene_map, conv_id))["battle"]  # no map for this scene: paint one
        return {"system": system, "enemies": scene_foes, "map": None, "battle": battle, "from_scene": True}
    msgs = s.conversations.list_messages(conv_id)[-6:]
    scene = "\n\n".join(f"{'PLAYER' if m['role'] == 'user' else 'GM'}: {m['content']}" for m in msgs)
    rules = ""
    scenario = s.conversations.get(conv_id)["scenario"]
    ids = s.rulebooks.ready_ids(scenario.get("rulebooks") or [])
    if ids:
        found = await s.rulebooks.search(ids, msgs[-1]["content"] if msgs else "", k=2)
        rules = "\n\n".join(f"{f['heading']}: {f['text']}" for f in found)
    return {"system": system, **(await suggest_fight(s.llm, system, scene, rules))}


@app.post("/api/conversations/{conv_id}/combat")
async def combat_action(conv_id: int, body: dict[str, Any] = Body(...)):
    """start | act | enemies | end. The app rolls, updates the fight, and sends the result to the GM, who narrates it."""
    s = svc()
    action = body.get("action")
    if action == "start":
        fight_map = body.get("map") if isinstance(body.get("map"), dict) else None
        if fight_map and fight_map.get("tiles") and not fight_map.get("background"):
            fight_map = await asyncio.to_thread(_paint_fight_map, fight_map)  # the little tile map becomes a painted picture

        def prepare(st):
            card = s.conversations.get(conv_id)["scenario"]
            allies = (body.get("allies") or []) + party.allies(st, card)  # companions always join
            new, line = s.combat.start(st, body.get("system", "d20"), BESTIARY.enrich(body.get("enemies") or []),
                                       allies, body.get("player") or {}, body.get("grid") or {},
                                       fight_map,
                                       body.get("near") if isinstance(body.get("near"), list) else None)
            if body.get("scene"):  # this scene's fight happened: the chat stops offering it
                adv_st = new.setdefault("adventure", {"scene": "", "visited": [], "xp_given": []})
                adv_st.setdefault("fought", []).append(str(body["scene"])[:60])
            fight5e.auto_reactions(new, library5e())  # 🛡 Shield / 🌀 Uncanny Dodge on enemy turns, when the sheet has them
            return new, line
    elif action == "act":
        def prepare(st):
            out = s.combat.player_action(st, body.get("move", "attack"), str(body.get("target", "")),
                                         str(body.get("advantage", "")), str(body.get("ability", "")))
            fight5e.settle_auto(out[0], library5e())
            return out
    elif action == "step":  # one part of the player's turn (attack, bonus strike, dodge…): rolled at once, no reply yet
        not_busy(conv_id)
        state = s.conversations.get_state(conv_id)
        if body.get("move") == "use":  # an option from the 5e list (Dash, Grapple, Second Wind, a spell…)
            state, line = await asyncio.to_thread(_use_option, s, state, str(body.get("option", "")), str(body.get("target", "")),
                                                  str(body.get("advantage", "")), as_int(body.get("slot"), 0) or None,
                                                  as_int(body.get("amount"), 0) or None, body.get("risk") is True)
        else:
            state, line = s.combat.player_step(state, str(body.get("move", "attack")), str(body.get("target", "")),
                                               str(body.get("advantage", "")), str(body.get("ability", "")))
        s.conversations.save_state(conv_id, state)
        return {"state": state, "line": line}
    elif action == "describe":  # "Want to describe it?": the player's words under the part of the turn just played
        not_busy(conv_id)
        state = s.combat.describe_last(s.conversations.get_state(conv_id), str(body.get("text", "")))
        s.conversations.save_state(conv_id, state)
        return {"state": state}
    elif action == "move":  # the player walks on the map (own turn, up to their speed); no reply from the GM
        not_busy(conv_id)
        state = s.combat.move_player(s.conversations.get_state(conv_id), body.get("x"), body.get("y"))
        s.conversations.save_state(conv_id, state)
        return {"state": state}
    elif action == "auto":  # turn an automatic reaction on or off (🛡 Shield, 🌀 Uncanny Dodge)
        not_busy(conv_id)
        state = s.conversations.get_state(conv_id)
        auto = (state.get("combat") or {}).setdefault("auto_reactions", {})
        if str(body.get("key")) in ("shield", "uncanny"):
            auto[str(body["key"])] = bool(body.get("on"))
        s.conversations.save_state(conv_id, state)
        return {"state": state}
    elif action == "enemies":
        def prepare(st):
            out = s.combat.enemies_act(st)
            fight5e.settle_auto(out[0], library5e())
            return out
    elif action == "end":
        prepare = lambda st: s.combat.end(st, str(body.get("reason", "")))  # noqa: E731
    else:
        raise CombatError("Unknown combat action.")
    return stream_response(s.engine.send(conv_id, str(body.get("text", "")), prepare=prepare))


def _use_option(s, state: dict, option_id: str, target: str, advantage: str, slot: int | None = None, amount: int | None = None,
                risk: bool = False):
    return fight5e.cast_in_fight(s.combat, state, library5e(), option_id, target, advantage, slot, amount, risk)


@app.get("/api/conversations/{conv_id}/combat/options")
async def combat_options(conv_id: int):
    """The 5e options for this turn, by cost (action, bonus action, reaction, free), and what is already spent."""
    from .dnd5e import actions
    from .dnd5e.character import derive as derive5e
    state = svc().conversations.get_state(conv_id)
    char = state.get("character5e")
    if not char:
        return {"groups": None}
    combat = state.get("combat") or {}
    lib = library5e()
    sheet = await asyncio.to_thread(derive5e, char, lib)
    return {"groups": await asyncio.to_thread(actions.options, char, lib), "spent": combat.get("spent") or {},
            "extra_actions": combat.get("extra_actions", 0), "reaction_used": combat.get("reaction_round") == combat.get("round"),
            "slots_left": sheet.get("slots_left", {}), "pact_left": sheet.get("pact_left", 0),
            "pact_level": (sheet.get("pact") or {}).get("level", 0), "auto": combat.get("auto_reactions") or {},
            "can_smite": bool((combat.get("last_hit") or {}).get("melee"))}


def _guess_kind(tiles: list[str]) -> str:
    text = "".join(tiles)
    count = {ch: text.count(ch) for ch in "#T~:"}
    if count[":"]:
        return "road"
    if count["~"] > len(text) // 20:
        return "river"
    if count["#"] > len(text) // 3:
        return "dungeon"
    return "forest" if count["T"] > len(text) // 8 else "field"


def _paint_fight_map(fight_map: dict) -> dict:
    """Paint a tile map (Combat tab's generated or saved map) as a picture lined up with its squares."""
    try:
        tiles = clean_map_tiles(fight_map["tiles"])
        kind = str(fight_map.get("type") or "")
        kind = kind if kind in MAP_TYPES else _guess_kind(tiles)
        url = f"/api/uploads/{save_upload(mappaint.paint(tiles, kind, len(''.join(tiles))), UPLOAD_DIR)}"
    except Exception:  # noqa: BLE001 - a picture is a nicety: the fight still runs on the plain tiles
        logging.getLogger("rpg").exception("could not paint the battle map")
        return fight_map
    return {**fight_map, "tiles": tiles, "background": url, "geom": mappaint.geometry(tiles), "painted": True}


def _paint_scene_map(conv_id: int, kind: str = "", seed: int | None = None, scene_id: str = "") -> dict:
    """Paint a map for an adventure scene that has none, and keep it in the card (and this game) as the scene's map."""
    import random as _r
    s = svc()
    conv = s.conversations.get(conv_id)
    adv = conv["scenario"].get("adventure") or {}
    state = s.conversations.get_state(conv_id)
    scene = adventure.get_scene(adv, scene_id or (state.get("adventure") or {}).get("scene", ""))
    if not scene:
        raise HTTPException(404, "There is no adventure scene to paint a map for.")
    kind = kind if kind in MAP_TYPES else adventure.pick_kind(scene)
    seed = seed if isinstance(seed, int) else _r.randrange(1_000_000)
    tiles = generate_map(kind, 24, 16, seed)
    url = f"/api/uploads/{save_upload(mappaint.paint(tiles, kind, seed), UPLOAD_DIR)}"
    new_adv = adventure.add_painted_map(adv, scene["id"], kind, tiles, url, mappaint.geometry(tiles))
    s.conversations.set_adventure(conv_id, new_adv)
    if conv.get("scenario_id"):
        card = s.scenarios.get(conv["scenario_id"])
        if card:
            card_adv = card["data"].get("adventure") or {}
            if adventure.get_scene(card_adv, scene["id"]):
                s.scenarios.update(card["id"], {**card["data"], "name": card["name"],
                                                "adventure": adventure.add_painted_map(card_adv, scene["id"], kind, tiles, url,
                                                                                       mappaint.geometry(tiles))})
    return {"battle": adventure.battle_map(new_adv, state), "kind": kind, "seed": seed, "scene": scene["id"]}


@app.post("/api/conversations/{conv_id}/adventure/paint-map")
async def adventure_paint_map(conv_id: int, body: dict[str, Any] = Body(default={})):
    """🎨 Paint a map for the current scene (or a new one: 🎲), like the map sites do, and use it for the fight."""
    seed = body.get("seed")
    return await asyncio.to_thread(_paint_scene_map, conv_id, str(body.get("kind") or ""),
                                   int(seed) if str(seed or "").isdigit() else None, str(body.get("scene") or ""))


@app.post("/api/conversations/{conv_id}/combat/paint-map")
async def combat_paint_map(conv_id: int, body: dict[str, Any] = Body(default={})):
    """A fight running on a plain grid gets a painted map: everyone is placed again on it."""
    s = svc()
    if s.engine.is_busy(conv_id):
        raise CombatError("Wait for the current reply to finish.")
    state = s.conversations.get_state(conv_id)
    combat = state.get("combat") or {}
    if not combat.get("active"):
        raise CombatError("There is no fight going on.")
    adv = s.conversations.get(conv_id)["scenario"].get("adventure") or {}
    if adventure.get_scene(adv, (state.get("adventure") or {}).get("scene", "")):
        battle = (await asyncio.to_thread(_paint_scene_map, conv_id, str(body.get("kind") or "")))["battle"]
        state = s.conversations.get_state(conv_id)
        combat = state["combat"]
    else:
        import random as _r
        kind = str(body.get("kind") or "")
        g = combat["grid"]
        tiles = g.get("tiles") or generate_map(kind if kind in MAP_TYPES else "field", min(24, g["w"]), min(24, g["h"]),
                                               _r.randrange(1_000_000))
        battle = await asyncio.to_thread(_paint_fight_map, {"tiles": tiles, "type": kind, "name": g.get("name") or ""})
    tiles = battle.get("tiles") or []
    w, h = (len(tiles[0]), len(tiles)) if tiles else (battle["w"], battle["h"])
    combat["grid"] = {"w": w, "h": h, "tiles": tiles, "background": battle.get("background", ""),
                      "name": str(battle.get("name") or "")[:60], "painted": bool(battle.get("painted")),
                      **combat_geometry(battle)}
    for c in combat["combatants"]:
        c["x"], c["y"] = -1, -1
    near = battle.get("near")
    s.combat._place(combat["combatants"], w, h, tiles, tuple(near) if near else None)
    s.conversations.save_state(conv_id, state)
    return {"state": state}


@app.patch("/api/conversations/{conv_id}/combat/{cid}")
async def combat_edit(conv_id: int, cid: str, body: dict[str, Any] = Body(...)):
    """Change HP, conditions or a position by hand (no message is sent)."""
    s = svc()
    if s.engine.is_busy(conv_id):
        raise CombatError("Wait for the current reply to finish.")
    state = s.combat.edit(s.conversations.get_state(conv_id), cid, body.get("hp"), body.get("conditions"), body.get("x"), body.get("y"))
    s.conversations.save_state(conv_id, state)
    return state


# ------------------------------------------------------------------ jukebox
@app.exception_handler(MusicError)
async def _music_error(_: Request, exc: MusicError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/api/music")
async def list_music():
    return {"tracks": svc().music.list(), "moods": list(MUSIC_MOODS)}


MB = 1024 * 1024
UPLOAD_LIMITS = {"picture": 8 * MB, "music": 100 * MB, "rulebook": 200 * MB, "skills": 25 * MB, "card": 300 * MB}


async def read_body(request: Request, kind: str) -> bytes:
    """The raw upload, refused with 413 as soon as it passes the size limit (it is never held whole in memory)."""
    limit = UPLOAD_LIMITS[kind]
    too_big = HTTPException(413, f"The file is too large (limit {limit // MB} MB).")
    try:
        if int(request.headers.get("content-length") or 0) > limit:
            raise too_big
    except ValueError:
        pass
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise too_big
        chunks.append(chunk)
    return b"".join(chunks)


@app.post("/api/music/upload")
async def upload_music(request: Request, name: str = Query(""), tags: str = Query("")):
    """A song from this PC, sent as the raw request body."""
    return svc().music.add_file(await read_body(request, "music"), name, tags.split(","))


@app.post("/api/music")
async def add_music_link(body: dict[str, Any] = Body(...)):
    return svc().music.add_link(str(body.get("url", "")), str(body.get("name", "")), body.get("tags"), body.get("cards"))


@app.patch("/api/music/{track_id}")
async def update_music(track_id: int, body: dict[str, Any] = Body(...)):
    return svc().music.update(track_id, body.get("name"), body.get("tags"), body.get("cards"))


@app.delete("/api/music/{track_id}")
async def delete_music(track_id: int):
    svc().music.delete(track_id)
    return {"deleted": True}


@app.get("/api/music/files/{name}")
async def music_file(name: str):
    path = svc().music.file_path(name)
    if not path:
        raise HTTPException(status_code=404, detail="Song not found")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable", "Accept-Ranges": "bytes"})


# ------------------------------------------------------------------ battle maps
@app.exception_handler(MapError)
async def _map_error(_: Request, exc: MapError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/api/maps")
async def list_maps():
    """Your saved maps, plus what the editor and generators offer."""
    return {"maps": svc().maps.list(), "types": list(MAP_TYPES), "features": list(MAP_FEATURES),
            "tiles": {k: v["name"] for k, v in MAP_TILES.items()}}


@app.post("/api/maps/generate")
async def make_map(body: dict[str, Any] = Body(default={})):
    """A map made by code from a type (forest, dungeon...). Same seed, same map."""
    import random as _r
    seed = body.get("seed")
    seed = int(seed) if str(seed or "").lstrip("-").isdigit() else _r.randrange(1_000_000)
    tiles = generate_map(str(body.get("type", "field")), int(body.get("w", 12) or 12), int(body.get("h", 8) or 8), seed,
                         [f for f in body.get("features", []) if isinstance(f, str)])
    return {"tiles": tiles, "seed": seed}


@app.post("/api/maps")
async def create_map(body: dict[str, Any] = Body(...)):
    return svc().maps.save(body)


@app.put("/api/maps/{map_id}")
async def update_map(map_id: int, body: dict[str, Any] = Body(...)):
    return svc().maps.save(body, map_id)


@app.delete("/api/maps/{map_id}")
async def delete_map(map_id: int):
    svc().maps.delete(map_id)
    return {"deleted": True}


@app.exception_handler(CombatError)
async def _combat_error(_: Request, exc: CombatError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(AreaRisk)
async def _area_risk(_: Request, exc: AreaRisk):
    """The spell's area would catch the caster or an ally: the page asks, then sends it again with `risk`."""
    return JSONResponse({"detail": str(exc), "confirm": "risk", "who": exc.who}, status_code=409)


# ------------------------------------------------------------------ rulebooks
@app.exception_handler(RulebookError)
async def _rulebook_error(_: Request, exc: RulebookError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/api/rulebooks")
async def list_rulebooks():
    return {"books": svc().rulebooks.list(), "ocr_available": ocr_available()}


_BACKGROUND: set = set()


async def _import_book(book_id: int, data: bytes, filename: str) -> None:
    book = await asyncio.to_thread(svc().rulebooks.import_bytes, book_id, data, filename)
    if book["status"] == "ready":
        try:
            await svc().rulebooks.embed_book(book_id)
        except Exception as exc:  # meaning-based search is optional; keyword search still works
            logging.getLogger("rpg").warning("Embedding the rulebook failed: %s", exc)


@app.post("/api/rulebooks")
async def upload_rulebook(request: Request, name: str = Query(""), system: str = Query("other"), filename: str = Query("")):
    """Upload a PDF, .txt or .md as the raw request body. Reading runs in the background; poll GET /api/rulebooks."""
    data = await read_body(request, "rulebook")
    if not data:
        raise RulebookError("The file is empty.")
    book = svc().rulebooks.create(name or filename.rsplit(".", 1)[0] or "Rulebook", system, filename)
    task = asyncio.create_task(_import_book(book["id"], data, filename))
    _BACKGROUND.add(task)  # keep a reference so the task is not garbage-collected
    task.add_done_callback(_BACKGROUND.discard)
    return book


@app.patch("/api/rulebooks/{book_id}")
async def update_rulebook(book_id: int, body: dict[str, Any] = Body(...)):
    return svc().rulebooks.update(book_id, body.get("name"), body.get("house_rules"), body.get("system"))


@app.delete("/api/rulebooks/{book_id}")
async def delete_rulebook(book_id: int):
    svc().rulebooks.delete(book_id)
    return {"deleted": True}


@app.get("/api/rulebooks/search")
async def search_rulebooks(q: str = Query(...), ids: str = Query("")):
    """Look something up in your rulebooks (all of them when `ids` is empty)."""
    book_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()] or [b["id"] for b in svc().rulebooks.list() if b["status"] == "ready"]
    return {"results": await svc().rulebooks.search(book_ids, q, k=6)}


# ------------------------------------------------------------------ AI drafts
@app.post("/api/drafts/card-field")
async def draft_field(body: dict[str, Any] = Body(...)):
    """Let the AI write one field of a card (opening, world, rules, tone, teaser) from the rest of the card."""
    card = body.get("card") if isinstance(body.get("card"), dict) else {}
    text = await draft_card_field(svc().llm, str(body.get("field", "")), card, str(body.get("hint", "")),
                                  card.get("language") or svc().settings.all().get("response_language", "en"))
    return {"text": text}


@app.post("/api/drafts/player")
async def draft_player_route(body: dict[str, Any] = Body(...)):
    """Suggest background, looks and personality for the player's character on the start screen."""
    scenario = svc().scenarios.get(int(body.get("scenario_id", 0))) if body.get("scenario_id") else None
    card = {**(scenario["data"] if scenario else {}), "name": scenario["name"] if scenario else ""}
    player = body.get("player") if isinstance(body.get("player"), dict) else {}
    return await draft_player(svc().llm, card, player, card.get("language") or svc().settings.all().get("response_language", "en"))


# ------------------------------------------------------------------ card import / export
@app.post("/api/cards/preview")
async def preview_card(body: dict[str, Any] = Body(...)):
    """Read a card file (Character Card V2/V1 or one exported by this app) without saving it."""
    return parse_card(body.get("card"))


@app.post("/api/cards/import")
async def import_card(body: dict[str, Any] = Body(...)):
    """Save an imported card. `skip` lists character names to leave out; `name` renames the card."""
    result = parse_card(body.get("card"))
    data = result["scenario"]
    skip = {str(n).lower() for n in body.get("skip", []) if n}
    if skip:
        data["npcs"] = [n for n in data["npcs"] if n["name"].lower() not in skip]
    if str(body.get("name", "")).strip():
        data["name"] = str(body["name"]).strip()
    return svc().scenarios.create(data)


# ------------------------------------------------------------------ this PC, and writing help
_HW: dict = {}


@app.get("/api/hardware")
async def hardware_info(refresh: bool = Query(False)):
    """The graphics card, memory and processor of this PC, and the roleplay model that fits best."""
    if refresh or not _HW:
        _HW.clear()
        _HW.update(await asyncio.to_thread(hardware.scan))
    return {**_HW, "suggestion": hardware.suggest(_HW)}


@app.post("/api/correct")
async def correct_text(body: dict = Body(...)):
    """✨ Correct my text: spelling and grammar fixed by the model, keeping the meaning and the writing marks."""
    text = str(body.get("text", ""))[:4000]
    if not text.strip():
        return {"text": text}
    lang = str(body.get("language") or svc().settings.get("response_language") or "en")
    return {"text": await writing_help.correct(svc().llm, text, lang)}


# ------------------------------------------------------------------ personas
@app.get("/api/personas")
async def personas_list():
    return svc().personas.list()


@app.post("/api/personas")
async def personas_create(body: dict = Body(...)):
    return svc().personas.save(body)


@app.put("/api/personas/{persona_id}")
async def personas_update(persona_id: int, body: dict = Body(...)):
    return svc().personas.save(body, persona_id)


@app.delete("/api/personas/{persona_id}")
async def personas_delete(persona_id: int):
    svc().personas.delete(persona_id)
    return {"deleted": True}


# ------------------------------------------------------------------ narration voice (Piper)
@app.get("/api/voice")
async def voice_status():
    return svc().voice.status()


@app.post("/api/voice/install")
async def voice_install(body: dict = Body(...)):
    """Download the voice program (once) and a voice, in the background; poll GET /api/voice."""
    voice = str(body.get("voice", ""))
    if voice not in VOICE_CATALOG:
        raise ValueError("Unknown voice.")
    async def run():
        try:
            await svc().voice.install(voice)
        except VoiceError as exc:  # shown in the Settings list
            logging.getLogger("rpg").warning("Voice download failed: %s", exc)
    background(run())
    await asyncio.sleep(0.05)
    return svc().voice.status()


@app.post("/api/voice/remove")
async def voice_remove(body: dict = Body(...)):
    return svc().voice.remove(str(body.get("voice", "")))


@app.get("/api/voice/speak/{message_id}")
async def voice_speak(message_id: int, voice: str = Query("")):
    """The message read aloud (a .wav made once, then kept)."""
    s = svc()
    msg = s.conversations.get_message(message_id)
    name = voice or s.settings.get("voice_name")
    if not name:
        raise ValueError("Pick a narration voice in Settings first.")
    path = await asyncio.to_thread(s.voice.speak, msg["content"], name, float(s.settings.get("voice_speed") or 1.0))
    return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "no-cache"})


# ------------------------------------------------------------------ backups and .caliope card files
@app.get("/api/backups")
async def backups_list():
    return {"folder": str(backups.backup_dir(svc().db.path)), "backups": backups.list_backups(svc().db.path)}


@app.post("/api/backups/now")
async def backups_now():
    s = svc()
    made = await asyncio.to_thread(backups.backup_now, s.db.conn, s.db._lock, s.db.path, int(s.settings.get("backups_keep") or 7), None, True)
    return {"made": made, "backups": backups.list_backups(s.db.path)}


@app.post("/api/backups/open")
async def backups_open():
    """Open the backups folder in Windows Explorer (this PC only)."""
    folder = backups.backup_dir(svc().db.path)
    folder.mkdir(parents=True, exist_ok=True)
    if not hasattr(os, "startfile"):
        raise ValueError(f"Open this folder yourself: {folder}")
    os.startfile(str(folder))  # noqa: S606 (a local folder of this app)
    return {"opened": str(folder)}


@app.get("/api/scenarios/{scenario_id}/export.caliope")
async def export_caliope(scenario_id: int):
    """The card and its pictures in one .caliope file, to share it without GitHub or the cloud."""
    sc, _ = _card_names(scenario_id)
    raw = await asyncio.to_thread(backups.pack_card, sc["data"], sc["name"],
                                  {"/api/cardpics/": CARDPIC_DIR, "/api/uploads/": UPLOAD_DIR}, PORTRAIT_DIR)
    fname = re.sub(r"[^A-Za-z0-9 _-]+", "", sc["name"]).strip() or "card"
    return Response(raw, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{fname}.caliope"'})


@app.post("/api/cards/import-caliope")
async def import_caliope(request: Request):
    raw = await read_body(request, "card")
    created = svc().scenarios.create({"name": "Importing…"})
    try:
        name, data = await asyncio.to_thread(backups.unpack_card, raw, CARDPIC_DIR / str(created["id"]) / "imported",
                                             f"/api/cardpics/{created['id']}/imported")
        return svc().scenarios.update(created["id"], {**data, "name": name})
    except Exception:  # nothing half-imported stays behind
        svc().scenarios.delete(created["id"])
        cardpics.remove_card_pictures(CARDPIC_DIR / str(created["id"]))
        raise


# ------------------------------------------------------------------ Cantos, recap and the map bag
@app.get("/api/conversations/{conv_id}/cantos")
async def cantos_list(conv_id: int):
    svc().conversations.get(conv_id)
    return svc().cantos.list(conv_id)


@app.post("/api/conversations/{conv_id}/cantos/close")
async def cantos_close(conv_id: int, body: dict = Body(default={})):
    """Write the chronicle of the current Canto and begin the next one."""
    if svc().engine.is_busy(conv_id):
        raise BusyError("Wait for the current reply to finish.")
    svc().conversations.get(conv_id)
    return await svc().cantos.close(conv_id, str(body.get("title", "")))


@app.patch("/api/cantos/{canto_id}")
async def cantos_rename(canto_id: int, body: dict = Body(...)):
    return svc().cantos.rename(canto_id, str(body.get("title", "")))


@app.post("/api/conversations/{conv_id}/warm")
async def warm_story(conv_id: int):
    """Let the built-in engine read this game's story now, so the first reply after opening it is quick."""
    svc().conversations.get(conv_id)
    background(svc().engine.warm(conv_id))
    return {"ok": True}


@app.post("/api/conversations/{conv_id}/recap")
async def recap(conv_id: int):
    """"Previously, in…": written only when asked, never added to the story."""
    conv = svc().conversations.get(conv_id)
    language = conv["scenario"].get("language") or svc().settings.get("response_language")
    return {"text": await svc().cantos.recap(conv_id, conv["title"], conv["summary"], language)}


BESTIARY = bestiary.Bestiary(Path(DB_PATH).parent / "bestiary")


@app.get("/api/bestiary")
async def bestiary_list():
    """🐉 Every monster sheet (backend/data/bestiary, one file per monster)."""
    return {"monsters": BESTIARY.list(), "books": BESTIARY.books(), "folder": str(BESTIARY.folder)}


@app.get("/api/bestiary/find")
async def bestiary_find(name: str = Query("")):
    """The sheet for an enemy's name ("Goblins" finds Goblin), with the numbers a fight uses."""
    m = BESTIARY.find(name)
    return {"monster": m, "combat": bestiary.combat_numbers(m) if m else None}


@app.post("/api/bestiary")
async def bestiary_save(body: dict[str, Any] = Body(...)):
    return BESTIARY.save(body.get("monster") or {}, str(body.get("old_id") or ""))


@app.post("/api/bestiary/open")
async def bestiary_open(body: dict[str, Any] = Body(default={})):
    """Open the Bestiary's folder (or one book's) in Windows Explorer."""
    folder = BESTIARY.folder / bestiary.book_folder(str(body.get("book") or ""))
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(folder))  # noqa: S606
    return {"folder": str(folder)}


@app.delete("/api/bestiary/{monster_id:path}")
async def bestiary_delete(monster_id: str):
    BESTIARY.delete(monster_id)
    return {"deleted": True}


@app.post("/api/bestiary/import")
async def bestiary_import(request: Request, replace: bool = Query(False), book: str = Query("")):
    """Read stat blocks from a text, Markdown or PDF (a book's monster appendix). Sheets already here are kept unless
    `replace`."""
    data = await read_body(request, "rulebook")
    if data[:5] == b"%PDF-":
        pages, _ = await asyncio.to_thread(read_pdf, data)
        text = "\n".join(pages)
    else:
        text = "\n".join(read_text(data))
    return _store_monsters(text, replace, book)


def _store_monsters(text: str, replace: bool = False, book: str = "") -> dict:
    """Every stat block in the text, saved in the book's own folder (bestiary/<book>/)."""
    added, kept = [], []
    book = bestiary.book_folder(book)
    have = {(m["book"], bestiary.slug(m["name"])) for m in BESTIARY.list()}
    for m in bestiary.parse_statblocks(text):
        if (book, bestiary.slug(m["name"])) in have and not replace:
            kept.append(m["name"])
            continue
        BESTIARY.save({**m, "book": book})
        added.append(m["name"])
    return {"added": added, "kept": kept, "book": book}


@app.post("/api/scenarios/{scenario_id}/adventure/import")
async def import_adventure(scenario_id: int, request: Request, part: str = Query(""), filename: str = Query("")):
    """A published adventure (PDF, .txt or .md as the raw body, or pasted text) split into scenes and added to the card.
    The book stays on this PC; the card editor then shows the scenes for checking."""
    s = svc()
    card = s.scenarios.get(scenario_id)
    if not card:
        raise NotFound(f"Scenario {scenario_id} not found")
    data = await read_body(request, "rulebook")
    if not data.strip():
        raise HTTPException(400, "The text is empty.")
    if data[:5] == b"%PDF-" or filename.lower().endswith(".pdf"):
        pages, _info = await asyncio.to_thread(read_pdf, data)
        text = "\n".join(pages)
    else:
        text = "\n".join(read_text(data))
    found = await asyncio.to_thread(adventure.split_adventure, text, part.strip()[:80])
    book = re.sub(r"\.(md|txt|pdf)$", "", filename, flags=re.I) if filename and filename != "pasted.txt" else card["name"]
    monsters = await asyncio.to_thread(_store_monsters, text, False, book)  # the book's stat blocks: bestiary/<book>/
    for sc in found["scenes"]:
        sc["enemies"] = [{**e, **{k: v for k, v in bestiary.combat_numbers(m).items() if k in ("hp", "ac", "attack_bonus", "damage", "init_bonus")}}
                         if (m := BESTIARY.find(e["name"])) else e for e in sc["enemies"]]
    if not found["scenes"] and not found["background"]:
        raise HTTPException(422, "No scenes were found in this text. Headings like '1. Cave Mouth' or 'Goblin Ambush' are needed.")
    d = dict(card["data"])
    d["adventure"] = adventure.merge(d.get("adventure"), found, title=card["name"])
    names = {n["name"].lower() for n in d.get("npcs") or []}
    added = []
    for n in found["npcs"]:
        if n["name"].lower() not in names:
            d.setdefault("npcs", []).append({"name": n["name"], "description": n["description"], "met": False})
            added.append(n["name"])
    first = next((x for x in found["scenes"] if x["read_aloud"]), None)
    if first and not str(d.get("opening_message") or "").strip():
        d["opening_message"] = first["read_aloud"]
    updated = s.scenarios.update(scenario_id, {**d, "name": card["name"]})
    return {"card": updated, "report": {
        "scenes": len(found["scenes"]), "read_aloud": sum(1 for x in found["scenes"] if x["read_aloud"]),
        "checks": sum(len(x["checks"]) for x in found["scenes"]), "enemies": sum(len(x["enemies"]) for x in found["scenes"]),
        "npcs": added, "background": bool(found["background"]), "monsters": len(monsters["added"])}}


@app.post("/api/conversations/{conv_id}/adventure/scene")
async def adventure_scene(conv_id: int, data: dict[str, Any] = Body(...)):
    """Go to a scene by hand (the Adventure tab's "Go here")."""
    s = svc()
    adv = s.conversations.get(conv_id)["scenario"].get("adventure") or {}
    state = s.conversations.get_state(conv_id)
    if not adventure.get_scene(adv, str(data.get("scene") or "")):
        raise HTTPException(404, "This card has no such scene.")
    adventure.move(adv, state, str(data["scene"]))
    s.conversations.save_state(conv_id, state)
    return {"state": state}


@app.post("/api/conversations/{conv_id}/adventure/no-fight")
async def adventure_no_fight(conv_id: int, data: dict[str, Any] = Body(...)):
    """"Not now" on a fight offer: this scene's fight is not offered again (it can still start from the Combat tab)."""
    s = svc()
    state = s.conversations.get_state(conv_id)
    st = state.setdefault("adventure", {"scene": "", "visited": [], "xp_given": []})
    scene = str(data.get("scene") or "")[:60]
    if scene and scene not in st.setdefault("fought", []):
        st["fought"].append(scene)
    s.conversations.save_state(conv_id, state)
    return {"state": state}


@app.post("/api/conversations/{conv_id}/adventure/xp")
async def adventure_xp(conv_id: int, data: dict[str, Any] = Body(...)):
    """Give a scene's XP award once: it is added to the sheet's XP field."""
    s = svc()
    adv = s.conversations.get(conv_id)["scenario"].get("adventure") or {}
    scene = adventure.get_scene(adv, str(data.get("scene") or ""))
    if not scene or not scene["xp"]:
        raise HTTPException(404, "This scene has no XP award.")
    state = s.conversations.get_state(conv_id)
    st = state.setdefault("adventure", {"scene": "", "visited": [], "xp_given": []})
    if scene["id"] in st.setdefault("xp_given", []):
        return {"state": state, "xp": 0}
    status = state.setdefault("card_status", {})
    key = next((k for k in status if k.strip().lower() in ("xp", "exp", "experience")), "XP")
    try:
        before = int(re.sub(r"[^0-9-]", "", str(status.get(key) or "0")) or 0)
    except ValueError:
        before = 0
    status[key] = str(before + scene["xp"])
    st["xp_given"].append(scene["id"])
    s.conversations.save_state(conv_id, state)
    return {"state": state, "xp": scene["xp"], "total": status[key]}


@app.get("/api/sheet-templates")
async def sheet_templates():
    """Ready sheets (D&D 5e, Tormenta20, Vampire...) a card or a game can use in the Status tab."""
    return {"templates": sheets.library()}


@app.post("/api/conversations/{conv_id}/sheet-template")
async def set_sheet_template(conv_id: int, data: dict[str, Any] = Body(...)):
    """Pick (or clear) this game's sheet. The values already kept stay."""
    text = str(data.get("text") or "")
    if text.strip() and not statusbook.PLACEHOLDER.search(text):
        raise HTTPException(400, "A sheet needs at least one [placeholder], like 'HP: [HP]'.")
    s = svc()
    s.conversations.set_sheet_template(conv_id, text)
    tpl = s.engine._status_template(s.conversations.get(conv_id)["scenario"], s.settings.all())
    last = s.conversations.last_message(conv_id)
    if tpl and last and last["role"] == "assistant":  # shown at once, not only after the next reply
        s.conversations.update_message_meta(last["id"], {"status": statusbook.render(tpl, s.conversations.get_state(conv_id),
                                                                                      s.conversations.list_npcs(conv_id))})
    return {"ok": True}


@app.post("/api/conversations/{conv_id}/systems")
async def change_systems(conv_id: int, data: dict[str, Any] = Body(...)):
    """The Sheet tab: install a part ({slot, item}) or set a stat ({stat, value}), checked by the card's rules."""
    not_busy(conv_id)
    s = svc()
    sys_def = s.conversations.get(conv_id)["scenario"].get("systems") or {}
    if not sys_def:
        raise HTTPException(400, "This game's card keeps no sheet of its own.")
    state = s.conversations.get_state(conv_id)
    st = systems.normalize_state(sys_def, state.get("systems"))
    day = (state.get("clock") or {}).get("minutes", 0) // 1440 + 1
    error = ""
    if data.get("slot"):
        error = systems.set_part(sys_def, st, str(data["slot"]), str(data.get("item") or ""))
    elif data.get("stat"):
        systems.apply_changes(sys_def, st, [{"stat": str(data["stat"]), "value": data.get("value")}])
    elif data.get("buy"):
        error = systems.buy(sys_def, st, str(data["buy"]))
    elif data.get("gain"):
        error = systems.gain(sys_def, st, str(data["gain"]))
    elif data.get("job") and data.get("act"):
        error = systems.board_act(sys_def, st, str(data["job"]), str(data["act"]), day)
    elif data.get("board") == "new" and sys_def.get("board"):
        from .util import extract_json
        raw = await s.llm.chat(systems.board_messages(sys_def, st, systems._card_text(s.conversations.get(conv_id)["scenario"])),
                               json_schema=systems.BOARD_SCHEMA, max_tokens=500, temperature=0.8)
        jobs = (extract_json(raw or "") or {}).get("jobs") or []
        if not systems.board_post(sys_def, st, jobs, day):
            error = "The Aedo didn't write usable jobs. Try again."
    elif data.get("duel"):
        error = systems.duel(sys_def, st, str(data["duel"]), bool(data.get("won")), day)
    elif data.get("step"):
        error = systems.step(sys_def, st, str(data["step"]), int(data.get("delta") or 1), day)
    if error:
        raise HTTPException(400, error)
    state["systems"] = st
    s.conversations.save_state(conv_id, state)
    return full_conversation(conv_id)


@app.post("/api/conversations/{conv_id}/card-status")
async def save_card_status(conv_id: int, data: dict[str, Any] = Body(...)):
    """✎ The card's own sheet edited in the Sheet tab: saved, and the status under the last reply shows it at once."""
    not_busy(conv_id)
    s = svc()
    tpl = s.engine._status_template(s.conversations.get(conv_id)["scenario"], s.settings.all())
    if not tpl:
        raise HTTPException(400, "This game keeps no sheet of its own.")
    state = s.conversations.get_state(conv_id)
    state["card_status"] = {**(state.get("card_status") or {}), **statusbook.clean_values(tpl, data.get("values") or {})}
    state["sheet_from_chat"] = True
    s.conversations.save_state(conv_id, state)
    last = s.conversations.last_message(conv_id)
    if last and last["role"] == "assistant":
        s.conversations.update_message_meta(last["id"], {"status": statusbook.render(tpl, state, s.conversations.list_npcs(conv_id))})
    return full_conversation(conv_id)


@app.post("/api/conversations/{conv_id}/epilogue")
async def epilogue(conv_id: int):
    """🏁 After the card's ending: the epilogue, kept in the chat (outside the story)."""
    not_busy(conv_id)
    conv = svc().conversations.get(conv_id)
    state = svc().conversations.get_state(conv_id)
    language = conv["scenario"].get("language") or svc().settings.get("response_language")
    text = await svc().cantos.epilogue(conv_id, conv["title"], conv["summary"], language, state["player"].get("name") or "")
    if not text:
        raise HTTPException(502, "The model did not write the epilogue. Is the model running?")
    msg = svc().conversations.add_message(conv_id, "assistant", text, {"ooc": True, "epilogue": True})
    return {"message": svc().conversations.get_message(msg["id"])}


@app.get("/api/conversations/{conv_id}/gallery")
async def gallery(conv_id: int):
    return svc().cantos.gallery(conv_id)


@app.post("/api/conversations/{conv_id}/gallery")
async def gallery_keep(conv_id: int, body: dict = Body(...)):
    msg = svc().conversations.get_message(int(body.get("message_id", 0)))
    pic = msg["meta"].get("scene_picture")
    if msg["conversation_id"] != conv_id or not pic:
        raise NotFound("That message has no scene picture.")
    kept = svc().cantos.keep(conv_id, msg["id"], pic, svc().conversations.get_state(conv_id), str(body.get("title", "")))
    svc().conversations.update_message_meta(msg["id"], {"kept_picture": kept["id"]})
    return {"picture": kept, "message": svc().conversations.get_message(msg["id"])}


@app.patch("/api/gallery/{pic_id}")
async def gallery_rename(pic_id: int, body: dict = Body(...)):
    return svc().cantos.rename_picture(pic_id, str(body.get("title", "")))


@app.delete("/api/gallery/{pic_id}")
async def gallery_remove(pic_id: int):
    row = svc().cantos.remove_picture(pic_id)
    if row and row.get("message_id"):
        try:
            svc().conversations.update_message_meta(row["message_id"], {}, drop=("kept_picture",))
        except NotFound:
            pass
    return {"removed": True}


# ------------------------------------------------------------------ the Muse (writer's room)
_MUSE_LOCK = asyncio.Lock()


@app.get("/api/muse")
async def muse_list():
    return svc().muse.list()


@app.post("/api/muse")
async def muse_create(body: dict = Body(default={})):
    return svc().muse.create(str(body.get("title", "")))


@app.get("/api/muse/{talk_id}")
async def muse_get(talk_id: int):
    return svc().muse.get(talk_id)


@app.patch("/api/muse/{talk_id}")
async def muse_rename(talk_id: int, body: dict = Body(...)):
    return svc().muse.rename(talk_id, str(body.get("title", "")))


@app.delete("/api/muse/{talk_id}")
async def muse_delete(talk_id: int):
    svc().muse.delete(talk_id)
    return {"deleted": True}


@app.post("/api/muse/{talk_id}/undo")
async def muse_undo(talk_id: int):
    svc().muse.undo_last(talk_id)
    return svc().muse.get(talk_id)


async def _one_at_a_time(events):
    if _MUSE_LOCK.locked():
        yield {"type": "error", "message": "The Muse is still busy with the last request."}
        return
    async with _MUSE_LOCK:
        async with aclosing(events) as stream:
            async for e in stream:
                yield e


async def _wiki_fetch(url: str) -> dict:
    """GET a wiki's API (public sites only; every redirect is checked again)."""
    import httpx
    from .images import validate_url

    async with httpx.AsyncClient(follow_redirects=False, timeout=25.0) as client:
        for _ in range(4):
            validate_url(url)
            resp = await client.get(url, headers={"User-Agent": "Caliope/2.18 (personal roleplay app; wiki research)"})
            if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                url = str(resp.url.join(resp.headers["location"]))
                continue
            resp.raise_for_status()
            return resp.json()
    raise wikiresearch.ResearchError("The wiki redirected too many times.")


@app.post("/api/research/find")
async def research_find(body: dict[str, Any] = Body(...)):
    """📚 The Muse looks for a work's wiki and lists its biggest character and lore pages."""
    try:
        wiki = await wikiresearch.find_wiki(_wiki_fetch, str(body.get("query") or ""))
        pages = await wikiresearch.list_pages(_wiki_fetch, wiki["api"])
    except wikiresearch.ResearchError:
        raise
    except Exception as exc:
        raise HTTPException(502, f"The wiki could not be reached ({exc}). Is the internet on?") from exc
    return {**wiki, **pages}


@app.post("/api/research/build")
async def research_build(body: dict[str, Any] = Body(...)):
    """Read the ticked pages and draft a card (streamed progress). With a talk, the Muse gets a research note."""
    api_url = str(body.get("api") or "")
    if not re.match(r"^https://[^/]+(/[a-z]{2}(-[a-z]{2})?)?/api\.php$", api_url):
        raise HTTPException(400, "Find the wiki first.")
    talk_id = body.get("talk_id")

    async def events():
        async for ev in wikiresearch.research(_wiki_fetch, api_url, str(body.get("sitename") or ""), str(body.get("work") or ""),
                                              [str(x) for x in body.get("characters") or []], [str(x) for x in body.get("lore") or []],
                                              str(body.get("language") or "")):
            if ev["type"] == "card" and talk_id:
                try:
                    svc().muse._add(int(talk_id), "assistant", ev["notes"])
                except Exception:
                    pass
            yield ev
    return stream_response(events())


@app.post("/api/muse/{talk_id}/message")
async def muse_message(talk_id: int, body: dict = Body(...)):
    svc().muse.get(talk_id)
    return stream_response(_one_at_a_time(svc().muse.talk(talk_id, str(body.get("content", "")))))


@app.post("/api/muse/{talk_id}/card")
async def muse_card(talk_id: int):
    svc().muse.get(talk_id)
    return stream_response(_one_at_a_time(svc().muse.make_card(talk_id)))


@app.post("/api/muse/{talk_id}/characters")
async def muse_characters(talk_id: int):
    svc().muse.get(talk_id)
    return stream_response(_one_at_a_time(svc().muse.make_characters(talk_id)))


@app.post("/api/scenarios/{scenario_id}/npcs/merge")
async def card_merge_characters(scenario_id: int, body: dict = Body(...)):
    """Add characters (from the Muse) to a card: a character with the same name (e.g. one made from a picture
    folder) gets its empty boxes filled; new names are added. Games using the card get them too (not met yet)."""
    sc, names = _card_names(scenario_id)
    incoming = [n for n in body.get("npcs") or [] if isinstance(n, dict) and str(n.get("name", "")).strip()][:20]
    data, added, updated = npcfill.merge_characters(sc["data"], incoming)
    svc().scenarios.update(scenario_id, {**data, "name": sc["name"]})
    card = svc().scenarios.get(scenario_id)
    by = {n["name"]: n for n in card["data"]["npcs"]}
    for r in svc().db.query("SELECT id FROM conversations WHERE scenario_id = ?", (scenario_id,)):
        for name in added + updated:
            n = by.get(name)
            row = svc().conversations.find_npc(r["id"], name)
            if not n:
                continue
            if not row:
                svc().conversations.add_npc(r["id"], name, description=n.get("description", ""), personality=n.get("personality", ""),
                                            speech_style=n.get("speech_style", ""), appearance=n.get("appearance"),
                                            portraits=n.get("portraits"), met=False)
            else:
                svc().conversations.update_npc(row["id"], **{k: n.get(k) for k in ("description", "personality", "speech_style")
                                                            if not str(row.get(k, "")).strip() and n.get(k)})
    return {"added": added, "updated": updated, "card": card}


@app.post("/api/cards/export")
async def card_to_file(body: dict = Body(...)):
    """A card the Muse made, as a standard Character Card file (without adding it to Calíope)."""
    return export_card(normalize_scenario(body.get("card") or {}))


# ------------------------------------------------------------------ a card's pictures from a folder on this PC
CARDPIC_DIR = Path(DB_PATH).parent / "cardpics"
PICTURES_DIR = APP_HOME / "Pictures"  # one folder per card, easy to find next to Play.bat: drop pictures straight in
NEW_CHARACTER = "__new__"


def _card_names(scenario_id: int) -> tuple[dict, list[str]]:
    sc = svc().scenarios.get(scenario_id)
    if not sc:
        raise NotFound("Card not found")
    return sc, [n["name"] for n in sc["data"].get("npcs", [])]


@app.post("/api/scenarios/{scenario_id}/pictures/browse")
async def card_pictures_browse(scenario_id: int):
    _card_names(scenario_id)
    if _PICKER.locked():
        raise HTTPException(409, "The folder picker is already open (it may be behind this window).")
    async with _PICKER:
        folder = await asyncio.to_thread(pick_folder, "Pick the folder with the character pictures")
    return {"folder": folder}


def _card_home(sc: dict) -> Path:
    """The card's folder in Calíope (Pictures/<card name>); its name is saved in the card, so renaming keeps it."""
    existing = str(sc["data"].get("pictures_folder") or "")
    folder = cardpics.card_folder(PICTURES_DIR, sc["name"], existing)
    if folder.name != existing:
        svc().scenarios.update(sc["id"], {**sc["data"], "name": sc["name"], "pictures_folder": folder.name})
    return folder


@app.get("/api/scenarios/{scenario_id}/pictures/home")
async def card_pictures_home(scenario_id: int):
    """Calíope's folder for this card's pictures (made if missing) and what it holds right now."""
    sc, names = _card_names(scenario_id)
    folder = _card_home(sc)
    return {"folder": str(folder), "scan": await asyncio.to_thread(cardpics.scan, str(folder), names)}


@app.post("/api/scenarios/{scenario_id}/pictures/open")
async def card_pictures_open(scenario_id: int):
    """Open the card's pictures folder in Windows Explorer, to drop pictures straight into it."""
    sc, _ = _card_names(scenario_id)
    folder = _card_home(sc)
    if os.name == "nt":
        os.startfile(str(folder))  # type: ignore[attr-defined]  # noqa: S606 (our own folder)
        return {"folder": str(folder)}
    raise HTTPException(400, f"Open this folder yourself: {folder}")


@app.post("/api/scenarios/{scenario_id}/pictures/import")
async def card_pictures_import(scenario_id: int, body: dict = Body(default={})):
    """🔍 Search: pick a folder anywhere on the PC (or paste its address); its pictures are copied into the card's
    Calíope folder, then shown like a scan (nothing changes in the card until Apply)."""
    sc, names = _card_names(scenario_id)
    src = str(body.get("folder") or "")
    if not src:
        if _PICKER.locked():
            raise HTTPException(409, "The folder picker is already open (it may be behind this window).")
        async with _PICKER:
            src = await asyncio.to_thread(pick_folder, "Pick the folder with the character pictures")
        if not src:
            return {"cancelled": True}
    folder = _card_home(sc)
    copied = await asyncio.to_thread(cardpics.import_folder, src, folder)
    return {"folder": str(folder), "copied": copied, "scan": await asyncio.to_thread(cardpics.scan, str(folder), names)}


@app.post("/api/scenarios/{scenario_id}/pictures/scan")
async def card_pictures_scan(scenario_id: int, body: dict = Body(...)):
    """Preview: which characters the folder's pictures belong to. Nothing changes yet."""
    _, names = _card_names(scenario_id)
    return await asyncio.to_thread(cardpics.scan, str(body.get("folder", "")), names)


@app.post("/api/scenarios/{scenario_id}/pictures/apply")
async def card_pictures_apply(scenario_id: int, body: dict = Body(...)):
    """Copy the pictures into the app and use them for the card (and, if asked, for games already using it)."""
    sc, names = _card_names(scenario_id)
    found = await asyncio.to_thread(cardpics.scan, str(body.get("folder", "")), names)
    loose = {u["folder"] for u in found["unmatched"]}  # only folders the scan listed can be assigned by hand
    raw_over = {str(k): str(v) for k, v in (body.get("overrides") or {}).items() if str(k) in loose}
    new_names = []  # "＋ Add as a new character": the folder's name becomes a character of the card
    for folder, who in raw_over.items():
        if who == NEW_CHARACTER:
            name = re.sub(r"\.(png|jpe?g|webp|gif)$", "", folder, flags=re.I).strip()[:60]
            if name and name.lower() not in {n.lower() for n in names + new_names}:
                new_names.append(name)
            raw_over[folder] = name
    names_all = names + new_names
    overrides = {k: v for k, v in raw_over.items() if v in names_all}
    labels = {n["name"]: {m["n"]: m["label"] for m in (n.get("portraits") or {}).get("moods", []) if m.get("n")}
              for n in sc["data"].get("npcs", [])}
    pics = await asyncio.to_thread(cardpics.apply, found, labels, CARDPIC_DIR / str(scenario_id),
                                   f"/api/cardpics/{scenario_id}", overrides)
    data = dict(sc["data"])
    data["npcs"] = [{**n, "portraits": pics[n["name"]]} if n["name"] in pics else n for n in data.get("npcs", [])]
    data["npcs"] += [{"name": n, "description": "", "met": False, "in_prompt": True, "relationship": 0,
                      "portraits": pics.get(n) or {}} for n in new_names]
    svc().scenarios.update(scenario_id, {**data, "name": sc["name"]})
    games = 0
    if body.get("update_games", True):
        rows = svc().db.query("SELECT id FROM conversations WHERE scenario_id = ?", (scenario_id,))
        for r in rows:
            touched = False
            for npc in svc().conversations.list_npcs(r["id"]):
                if npc["name"] in pics:
                    svc().conversations.update_npc(npc["id"], portraits=pics[npc["name"]])
                    touched = True
            for n in new_names:  # new characters join games already using the card (not met yet)
                if not svc().conversations.find_npc(r["id"], n):
                    svc().conversations.add_npc(r["id"], n, portraits=pics.get(n), met=False)
                    touched = True
            games += touched
    return {"characters": len(pics), "new": new_names, "games": games, "card": svc().scenarios.get(scenario_id)}


@app.post("/api/scenarios/{scenario_id}/npcs/fill")
async def card_fill_characters(scenario_id: int, body: dict = Body(default={})):
    """Write the empty looks / personality / speech boxes of the card's characters (from what the card says, the rest
    invented once to fit), save them in the card and in games already using it. Streams progress."""
    _card_names(scenario_id)
    wanted = {str(n) for n in body.get("names") or []}

    async def run():
        sc = svc().scenarios.get(scenario_id)
        todo = [n for n in sc["data"].get("npcs", []) if (not wanted or n["name"] in wanted) and npcfill.missing(n)]
        if not todo:
            yield {"type": "done", "filled": 0, "card": sc}
            return
        filled = 0
        for i, npc in enumerate(todo, 1):
            yield {"type": "progress", "step": f"{npc['name']} ({i} of {len(todo)})"}
            try:
                values = await npcfill.fill_one(svc().llm, sc["data"], npc)
            except Exception as exc:  # the model went away: keep what is done
                yield {"type": "error", "message": f"Stopped at {npc['name']}: {exc}"}
                break
            if not values:
                continue
            sc = svc().scenarios.get(scenario_id)  # saved after each one, so stopping keeps the work
            data = dict(sc["data"])
            data["npcs"] = [npcfill.merge(n, values) if n["name"] == npc["name"] else n for n in data["npcs"]]
            svc().scenarios.update(scenario_id, {**data, "name": sc["name"]})
            done_npc = next((n for n in data["npcs"] if n["name"] == npc["name"]), None)
            if done_npc:  # shown in the editor right away, one character at a time
                yield {"type": "filled", "npc": done_npc}
            for r in svc().db.query("SELECT id FROM conversations WHERE scenario_id = ?", (scenario_id,)):
                row = svc().conversations.find_npc(r["id"], npc["name"])
                if row:  # running games: only boxes that are still empty there
                    keep = {k: v for k, v in values.items() if k in npcfill.missing(row)}
                    if keep:
                        merged = npcfill.merge(row, keep)
                        svc().conversations.update_npc(row["id"], appearance=merged["appearance"],
                                                       personality=merged["personality"], speech_style=merged["speech_style"])
            filled += 1
        yield {"type": "done", "filled": filled, "card": svc().scenarios.get(scenario_id)}

    return stream_response(run())


@app.post("/api/scenarios/{scenario_id}/pictures/r2")
async def card_pictures_to_r2(scenario_id: int):
    """Upload the card's pictures (the ones in the app's folder) to your private R2 bucket and use them from there."""
    sc, _ = _card_names(scenario_id)
    settings = svc().settings.all()
    if not r2.ready(settings):
        raise ValueError("Add the R2 account ID, bucket and keys in Settings > Pictures in the cloud first.")
    prefix = f"/api/cardpics/{scenario_id}/"
    slug = re.sub(r"[^a-z0-9]+", "-", sc["name"].lower()).strip("-") or f"card-{scenario_id}"
    moved: dict[str, str] = {}

    async def put(url: str) -> str:
        if not url.startswith(prefix):
            return url
        if url not in moved:
            base = (CARDPIC_DIR / str(scenario_id)).resolve()
            path = (base / url[len(prefix):]).resolve()
            if base not in path.parents or not path.is_file():
                return url  # a picture that is missing (or a link that points elsewhere) stays as it is
            data = path.read_bytes()
            ctype = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}.get(path.suffix, "")
            moved[url] = await r2.upload(settings, f"cards/{slug}/{url[len(prefix):]}", data, ctype)
        return moved[url]

    async def remap(p: dict) -> dict:
        return {"default": await put(p.get("default") or ""),
                "moods": [{**m, "url": await put(m["url"])} for m in p.get("moods") or []]}

    data = dict(sc["data"])
    data["npcs"] = [{**n, "portraits": await remap(n.get("portraits") or {})} for n in data.get("npcs", [])]
    svc().scenarios.update(scenario_id, {**data, "name": sc["name"]})
    by_name = {n["name"]: n["portraits"] for n in data["npcs"]}
    for r in svc().db.query("SELECT id FROM conversations WHERE scenario_id = ?", (scenario_id,)):
        for npc in svc().conversations.list_npcs(r["id"]):
            if npc["name"] in by_name and any(u.startswith(prefix) for u in _urls(npc["portraits"])):
                svc().conversations.update_npc(npc["id"], portraits=by_name[npc["name"]])
    return {"uploaded": len(moved), "card": svc().scenarios.get(scenario_id)}


def _urls(p: dict) -> list[str]:
    return [p.get("default") or ""] + [m.get("url", "") for m in p.get("moods") or []]


@app.get("/api/cardpics/{scenario_id}/{who}/{name}")
async def card_picture(scenario_id: int, who: str, name: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", who) or not re.fullmatch(r"\d{1,4}\.(png|jpg|webp|gif)", name):
        raise HTTPException(status_code=404, detail="Picture not found")
    path = CARDPIC_DIR / str(scenario_id) / who / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Picture not found")
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


@app.get("/api/scenarios/{scenario_id}/export")
async def export_scenario(scenario_id: int):
    scenario = svc().scenarios.get(scenario_id)
    if not scenario:
        raise NotFound(f"Scenario {scenario_id} not found")
    data = {**scenario["data"], "name": scenario["name"]}
    filename = "".join(c if c.isalnum() or c in "-_ " else "_" for c in scenario["name"]).strip() or "card"
    return JSONResponse(export_card(data), headers={"Content-Disposition": f'attachment; filename="{filename}.json"'})


PORTRAIT_DIR = Path(DB_PATH).parent / "portraits"
UPLOAD_DIR = PORTRAIT_DIR / "uploads"


@app.post("/api/uploads")
async def upload_picture(request: Request):
    """A picture from this PC (sent as the raw request body). Returns a link the app can use as a portrait."""
    data = await read_body(request, "picture")
    try:
        name = save_upload(data, UPLOAD_DIR)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"url": f"/api/uploads/{name}"}


@app.get("/api/uploads/{name}")
async def uploaded_picture(name: str):
    if not re.match(UPLOAD_NAME, name) or not (UPLOAD_DIR / name).is_file():
        raise HTTPException(status_code=404, detail="Picture not found")
    return FileResponse(UPLOAD_DIR / name, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/api/portrait")
async def portrait(url: str = Query(...)):
    """A character picture, downloaded once from its link and then served from this PC."""
    try:
        if r2.is_r2(url):  # a picture in your private R2 bucket: a short-lived signed link, then kept on this PC
            link = r2.download_link(svc().settings.all(), url)
            path = await get_image(url, PORTRAIT_DIR, fetch=lambda _u: http_fetch(link, timeout=60.0), check=lambda u: u)
        elif is_pixai(url):  # a scene picture painted by PixAI with your key, then kept on this PC
            s = svc().settings
            async def fetch(u):
                return await http_fetch(await pixai_paint(u, s.get("pixai_api_key"), s.get("pixai_model")), timeout=60.0)
            path = await get_image(url, PORTRAIT_DIR, fetch=fetch, check=lambda u: u)
        elif is_pollinations(url):  # a scene picture: painted on demand, one at a time, can take up to a minute
            fetch = lambda u: polite_fetch(u, lambda x: http_fetch(x, timeout=120.0))  # noqa: E731
            path = await get_image(url, PORTRAIT_DIR, fetch=fetch)
        else:
            path = await get_image(url, PORTRAIT_DIR)
    except (ImageError, PixAIError, r2.R2Error) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # network problems: the picture just doesn't show
        raise HTTPException(status_code=502, detail=f"Could not download the picture: {exc}") from exc
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800"})


# ------------------------------------------------------------------ conversations
@app.get("/api/conversations")
async def list_conversations():
    return svc().conversations.list()


@app.post("/api/conversations")
async def create_conversation(body: dict[str, Any] = Body(default={})):
    scenario = None
    if body.get("scenario_id") is not None:
        scenario = svc().scenarios.get(as_int(body["scenario_id"], 0))
        if not scenario:
            raise NotFound("Scenario not found")
    player = body.get("player") if isinstance(body.get("player"), dict) else None
    conv = svc().conversations.create(scenario, title=str(body.get("title", "")), player_name=body.get("player_name"),
                                      start=str(body.get("start") or ""),
                                      party_mode=str(body.get("party") or ""),
                                      player=player, setup=str(body.get("setup") or ""),
                                      card_status=body.get("card_status") if isinstance(body.get("card_status"), dict) else None,
                                      companions=body.get("companions") if isinstance(body.get("companions"), list) else None,
                                      abilities=body.get("abilities") if isinstance(body.get("abilities"), list) else None,
                                      systems_state=body.get("systems_state") if isinstance(body.get("systems_state"), dict) else None,
                                      player_lore=body.get("player_lore") if isinstance(body.get("player_lore"), list) else None)
    return full_conversation(conv["id"])


@app.post("/api/conversations/{conv_id}/restart")
async def restart_conversation(conv_id: int, body: dict[str, Any] = Body(default={})):
    """↺ Restart: a new game of the same card from its opening, same character with full HP; the old run kept or deleted."""
    s = svc()
    not_busy(conv_id)
    conv = s.conversations.get(conv_id)
    card = s.scenarios.get(conv["scenario_id"]) if conv.get("scenario_id") else None
    new = s.conversations.restart(conv_id, card, keep=body.get("keep", True) is not False)
    return full_conversation(new["id"])


@app.post("/api/conversations/{conv_id}/refresh-card")
async def refresh_from_card(conv_id: int):
    """⟳ This game takes its card's current version (new characters, lore, rules); the story and relationships stay."""
    s = svc()
    not_busy(conv_id)
    conv = s.conversations.get(conv_id)
    card = s.scenarios.get(conv["scenario_id"]) if conv.get("scenario_id") else None
    if not card:
        raise HTTPException(404, "This game's card no longer exists.")
    done = s.conversations.refresh_from_card(conv_id, card)
    return {**full_conversation(conv_id), "refreshed": done}


def _card_has_resources(conv_id: int) -> bool:
    sid = svc().conversations.get(conv_id)["scenario_id"]
    card = svc().scenarios.get(sid) if sid else None
    return bool(card and card["data"].get("resources"))


def not_busy(conv_id: int) -> None:
    if svc().engine.is_busy(conv_id):
        raise BusyError("Wait for the current reply to finish.")


def _status_now(conv_id: int) -> str:
    """The sheet as it stands, so the Status tab shows it before the first reply too."""
    s = svc()
    tpl = s.engine._status_template(s.conversations.get(conv_id)["scenario"], s.settings.all())
    return statusbook.render(tpl, s.conversations.get_state(conv_id), s.conversations.list_npcs(conv_id)) if tpl else ""


def _systems_view(conv_id: int) -> dict | None:
    s = svc()
    sys_def = s.conversations.get(conv_id)["scenario"].get("systems") or {}
    if not sys_def:
        return None
    st = systems.normalize_state(sys_def, s.conversations.get_state(conv_id).get("systems"))
    state = s.conversations.get_state(conv_id)
    day = (state.get("clock") or {}).get("minutes", 0) // 1440 + 1
    return {"systems": sys_def, "state": st, "computed": systems.compute(sys_def, st), "day": day,
            "board_due": bool(sys_def.get("board")) and systems.board_stale(sys_def, st, day),
            "prices": {i["name"]: systems.price_of(sys_def, i) for i in (sys_def.get("loadout") or {}).get("catalog") or []}}


def full_conversation(conv_id: int) -> dict:
    s = svc()
    return {
        "conversation": s.conversations.get(conv_id),
        "messages": s.conversations.list_messages(conv_id),
        "state": s.conversations.get_state(conv_id),
        "npcs": s.conversations.list_npcs(conv_id),
        "memory_count": s.memory.count(conv_id),
        "pinned_limit": int(s.settings.get("pinned_memory_limit")),
        "features": resolve_features(s.conversations.get(conv_id)["scenario"], s.settings.all()),
        "status_fields": statusbook.custom_fields(statusbook.template_of(s.conversations.get(conv_id)["scenario"]) or ""),
        "systems_view": _systems_view(conv_id),
        "status_form": statusbook.sheet_form(statusbook.template_of(s.conversations.get(conv_id)["scenario"]) or "",
                                             s.conversations.get_state(conv_id).get("card_status")),
        "status_by_app": bool(s.engine._status_template(s.conversations.get(conv_id)["scenario"], s.settings.all())),
        "sheet_own": bool(statusbook.template_of({**s.conversations.get(conv_id)["scenario"], "sheet_template": ""})),
        "status_now": _status_now(conv_id),
        "card_has_resources": _card_has_resources(conv_id),
        "cantos": s.cantos.list(conv_id),
    }


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: int):
    return full_conversation(conv_id)


@app.patch("/api/conversations/{conv_id}")
async def rename_conversation(conv_id: int, body: dict[str, Any] = Body(...)):
    return svc().conversations.rename(conv_id, str(body.get("title", "")))


@app.put("/api/conversations/{conv_id}/pinned")
async def set_pinned(conv_id: int, body: dict[str, Any] = Body(...)):
    """The "remember this" box: text the AI always sees and never forgets (limited in size)."""
    limit = int(svc().settings.get("pinned_memory_limit"))
    return svc().conversations.set_pinned(conv_id, str(body.get("text", "")), limit)


@app.put("/api/conversations/{conv_id}/player-lore")
async def set_player_lore(conv_id: int, body: dict[str, Any] = Body(...)):
    """The player's own lore entries for this game (canon, they win over the card's lore)."""
    return svc().conversations.set_player_lore(conv_id, body.get("entries"))


@app.post("/api/conversations/{conv_id}/player-lore/suggest")
async def suggest_player_lore(conv_id: int, body: dict[str, Any] = Body(...)):
    """New facts the story established about one entry (the player chooses which to add)."""
    conv = svc().conversations.get(conv_id)
    entry = next((e for e in conv["player_lore"] if e["id"] == body.get("id")), None)
    if not entry:
        raise NotFound("Lore entry not found")
    recent = [m["content"] for m in reversed(svc().conversations.list_messages(conv_id, after_id=conv["summary_upto"]))]
    text = await svc().llm.chat([{"role": "user", "content": suggest_prompt(entry, conv["summary"], recent)}],
                                max_tokens=250, temperature=0.3)
    return {"suggestions": parse_suggestions(text)}


@app.get("/api/calendar/presets")
async def calendar_presets():
    return worldtime.PRESETS


@app.post("/api/calendar/preview")
async def calendar_preview(body: dict[str, Any] = Body(...)):
    cal = worldtime.normalize_calendar({**body, "enabled": True})
    return {"calendar": cal, "starts": worldtime.format_now(cal, 0), "year_days": worldtime.year_days(cal)}


@app.post("/api/conversations/{conv_id}/events")
async def add_event(conv_id: int, body: dict[str, Any] = Body(...)):
    """An appointment the player adds by hand ("Sunday: Mira's festival")."""
    not_busy(conv_id)
    cal = svc().conversations.get(conv_id)["scenario"].get("calendar") or {}
    if not cal.get("enabled"):
        raise ValueError("This card has no calendar.")
    state = svc().conversations.get_state(conv_id)
    if not worldtime.add_event(state, cal, str(body.get("text", "")), str(body.get("when", ""))):
        raise ValueError("Write what happens and when (for example: Sunday, tomorrow at noon, in 3 days, 10 Frostmoon).")
    svc().conversations.save_state(conv_id, state)
    return state


@app.delete("/api/conversations/{conv_id}/events/{event_id}")
async def delete_event(conv_id: int, event_id: str):
    not_busy(conv_id)
    state = svc().conversations.get_state(conv_id)
    state["events"] = [e for e in state.get("events", []) if e["id"] != event_id]
    svc().conversations.save_state(conv_id, state)
    return state


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: int):
    not_busy(conv_id)
    svc().conversations.delete(conv_id)
    return {"deleted": True}


@app.post("/api/conversations/{conv_id}/chat")
async def chat(conv_id: int, body: dict[str, Any] = Body(...)):
    s = svc()
    s.conversations.get(conv_id)
    text = str(body.get("content", ""))
    combat = s.conversations.get_state(conv_id).get("combat") or {}
    intent = combat_intent(combat, text)
    if intent:  # "I swing at the goblin's neck" / "/attack goblin 2": the app rolls it, the GM narrates it in the player's words
        move, target, words = intent  # a typed message is the whole turn: the action, a bonus strike if named, then the turn ends
        moves, bonus_target = [move], ""
        if move == "attack" and bonus_intent(text):
            act_words, bonus_words = split_turn(words)
            target = find_target(combat, act_words) or target
            bonus_target = find_target(combat, bonus_words) if bonus_words else ""
            moves.append("bonus_attack")
        return stream_response(s.engine.send(conv_id, words, prepare=lambda st: s.combat.player_turn(st, moves, target, "", bonus_target)))
    if combat.get("active") and end_intent(text):  # "/end" or "I end my turn": the parts already played are narrated, others act
        return stream_response(s.engine.send(conv_id, text, prepare=lambda st: s.combat.player_action(st, "end")))
    return stream_response(s.engine.send(conv_id, text))


@app.post("/api/conversations/{conv_id}/check")
async def roll_check(conv_id: int, body: dict[str, Any] = Body(...)):
    """Roll a check the GM asked for in its last reply (bonus from the sheet) and send the result to the GM."""
    s = svc()
    last = s.conversations.last_message(conv_id)
    asked = (last or {}).get("meta", {}).get("checks") or []
    if not last or last["role"] != "assistant" or last["id"] != int(body.get("message_id", 0)):
        raise ValueError("Only a check from the GM's last reply can be rolled.")
    index = int(body.get("index", 0))
    if not 0 <= index < len(asked):
        raise ValueError("That check is not in the reply.")
    mode = str(body.get("mode", ""))
    not_busy(conv_id)
    state = s.conversations.get_state(conv_id)
    if (state.get("combat") or {}).get("active"):
        s.combat.use_reaction(state)  # one check per round in a fight
        s.conversations.save_state(conv_id, state)
    line = roll_line(s.dice, state, asked[index], mode if mode in ("advantage", "disadvantage") else "")
    return stream_response(s.engine.send(conv_id, line))


@app.post("/api/conversations/{conv_id}/buy")
async def buy_offer(conv_id: int, body: dict[str, Any] = Body(...)):
    """Buy something the GM's last reply offered: the app takes the money and puts the item in the bag."""
    s = svc()
    last = s.conversations.last_message(conv_id)
    offers = (last or {}).get("meta", {}).get("offers") or []
    if not last or last["role"] != "assistant" or last["id"] != int(body.get("message_id", 0)):
        raise ValueError("Only things offered in the GM's last reply can be bought.")
    index = int(body.get("index", 0))
    if not 0 <= index < len(offers):
        raise ValueError("That offer is not in the reply.")
    currency = s.conversations.get(conv_id)["scenario"].get("currency") or "gold"
    shop.buy(s.conversations.get_state(conv_id), offers[index], int(body.get("qty", 1)), currency)  # fails early when too poor
    return stream_response(s.engine.send(conv_id, "", prepare=lambda st: shop.buy(st, offers[index], int(body.get("qty", 1)), currency),
                                         kind="trade"))


@app.post("/api/conversations/{conv_id}/pay")
async def pay_someone(conv_id: int, body: dict[str, Any] = Body(...)):
    """Pay someone from the Bag tab: the app takes the money and tells the GM."""
    s = svc()
    currency = s.conversations.get(conv_id)["scenario"].get("currency") or "gold"
    args = (as_int(body.get("amount", 0), 0), str(body.get("to", "")), str(body.get("why", "")), currency)
    shop.pay(s.conversations.get_state(conv_id), *args)
    return stream_response(s.engine.send(conv_id, "", prepare=lambda st: shop.pay(st, *args), kind="trade"))


@app.post("/api/conversations/{conv_id}/ability")
async def use_ability(conv_id: int, body: dict[str, Any] = Body(...)):
    """Use an ability from the sheet outside a fight: the app pays its cost, rolls it and tells the GM."""
    s = svc()
    state = s.conversations.get_state(conv_id)
    if (state.get("combat") or {}).get("active"):
        raise ValueError("A fight is going on: use the ability from the Combat tab.")
    ability = next((a for a in state.get("abilities") or [] if a["id"] == str(body.get("ability", ""))), None)
    if not ability:
        raise ValueError("That ability is not on your sheet.")
    why = resources.can_pay(state, ability["costs"])
    if why:
        raise ValueError(why)
    return stream_response(s.engine.send(conv_id, str(body.get("text", "")),
                                         prepare=lambda st: resources.use_outside_combat(st, ability, s.dice), kind="ability"))


@app.post("/api/conversations/{conv_id}/rest")
async def rest(conv_id: int, body: dict[str, Any] = Body(...)):
    """Short rest (an hour) or long rest (a night): refills resources by their rules; a long rest also heals."""
    s = svc()
    kind = "long" if body.get("kind") == "long" else "short"
    cal = s.conversations.get(conv_id)["scenario"].get("calendar") or {}
    if cal.get("enabled"):  # with a calendar the clock moves too
        return stream_response(s.engine.send(conv_id, "/wait 8 hours" if kind == "long" else "/wait 1 hour"))

    def prepare(st):
        back = resources.regenerate(st, f"{kind}_rest")
        if kind == "long" and st["player"]["hp"]["current"] < st["player"]["hp"]["max"]:
            st["player"]["hp"]["current"] = st["player"]["hp"]["max"]
            back.append(f"HP {st['player']['hp']['max']}/{st['player']['hp']['max']}")
        what = "A night's rest" if kind == "long" else "A short rest"
        return st, f"\U0001F6CC {what}." + (f" Recovered: {', '.join(back)}." if back else "")
    return stream_response(s.engine.send(conv_id, "", prepare=prepare, kind="rest"))


@app.post("/api/conversations/{conv_id}/resources/sync")
async def sync_resources(conv_id: int):
    """Bring the card's current resources and powers into this game (a card edited after the game started).
    Pools that already exist keep their current value."""
    s = svc()
    not_busy(conv_id)
    conv = s.conversations.get(conv_id)
    card = s.scenarios.get(conv["scenario_id"]) if conv["scenario_id"] else None
    if not card or not card["data"].get("resources"):
        raise ValueError("The card has no resources yet. Add them in the card editor (Resources and powers).")
    state = s.conversations.get_state(conv_id)
    pools = resources.start_pools(card["data"]["resources"])
    for name, p in pools.items():
        old = (state.get("resources") or {}).get(name)
        if old:
            p["current"] = min(p["max"], old["current"])
    state["resources"] = pools
    state["abilities"] = [dict(a) for a in card["data"].get("abilities") or []]
    s.conversations.save_state(conv_id, state)
    return state


@app.post("/api/resources/suggest")
async def suggest_resources(body: dict[str, Any] = Body(...)):
    """The AI proposes resources (Mana, Aura...) and abilities for a card; the card editor shows them to confirm."""
    card = body.get("card") if isinstance(body.get("card"), dict) else {}
    info = card.get("information") or {}
    text = "\n\n".join(str(x) for x in (card.get("name"), card.get("world"), card.get("system_rules"), info.get("description"),
                                         info.get("scenario"), info.get("post_history")) if x)
    return await resources.suggest(svc().llm, text)


@app.post("/api/conversations/{conv_id}/regenerate")
async def regenerate(conv_id: int):
    svc().conversations.get(conv_id)
    return stream_response(svc().engine.regenerate(conv_id))


@app.post("/api/conversations/{conv_id}/messages/{message_id}/scene-picture")
async def scene_picture(conv_id: int, message_id: int, body: dict[str, Any] = Body(default={})):
    """Paint the scene of a GM reply (reroll=true: same description, another version)."""
    return await svc().engine.paint_scene(conv_id, message_id, bool(body.get("reroll")))


@app.post("/api/conversations/{conv_id}/fork")
async def fork_conversation(conv_id: int, body: dict[str, Any] = Body(...)):
    """Save point: copy the game up to a message into a new game."""
    if not as_int(body.get("message_id"), 0):
        raise ValueError("Choose the message to start the new game from.")
    return full_conversation(svc().engine.fork(conv_id, as_int(body["message_id"], 0)))


@app.get("/api/conversations/{conv_id}/export")
async def export_conversation(conv_id: int):
    """The whole story as a Markdown file (status blocks and portrait tags left out)."""
    from fastapi.responses import PlainTextResponse
    text = export_markdown(svc().conversations.get(conv_id), svc().conversations.list_messages(conv_id),
                           svc().conversations.get_state(conv_id))
    name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in svc().conversations.get(conv_id)["title"]).strip()[:60] or "story"
    return PlainTextResponse(text, media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="{name}.md"'})


@app.post("/api/conversations/{conv_id}/continue")
async def continue_reply(conv_id: int):
    return stream_response(svc().engine.continue_reply(conv_id))


@app.post("/api/conversations/{conv_id}/undo")
async def undo(conv_id: int):
    svc().conversations.get(conv_id)
    not_busy(conv_id)
    result = svc().engine.undo(conv_id)
    return {**result, **full_conversation(conv_id)}


@app.patch("/api/messages/{message_id}")
async def edit_message(message_id: int, body: dict[str, Any] = Body(...)):
    """Edit the text of one message in place (sheet and memories are not touched)."""
    return svc().engine.edit_message(message_id, str(body.get("content", "")))


@app.post("/api/conversations/{conv_id}/rewind")
async def rewind(conv_id: int, body: dict[str, Any] = Body(...)):
    """Remove everything after a message (and the message itself if inclusive=true)."""
    svc().conversations.get(conv_id)
    result = svc().engine.rewind(conv_id, int(body.get("message_id", 0)), bool(body.get("inclusive", False)))
    return {**result, **full_conversation(conv_id)}


@app.post("/api/conversations/{conv_id}/messages/{message_id}/resend")
async def resend(conv_id: int, message_id: int, body: dict[str, Any] = Body(...)):
    """Edit one of your messages, discard what came after it and stream a new reply."""
    svc().conversations.get(conv_id)
    svc().conversations.get_message(message_id)
    return stream_response(svc().engine.resend(conv_id, message_id, str(body.get("content", ""))))


@app.post("/api/conversations/{conv_id}/messages/{message_id}/sheet")
async def sheet_from_message(conv_id: int, message_id: int):
    """📋 on one of your messages: read the character sheet written there into the Sheet and Status tabs."""
    svc().conversations.get(conv_id)
    try:
        return await svc().engine.sheet_from_message(conv_id, message_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# -------------------------------------------------------------------------- state
@app.get("/api/conversations/{conv_id}/state")
async def get_state(conv_id: int):
    return svc().conversations.get_state(conv_id)


@app.patch("/api/conversations/{conv_id}/state")
async def patch_state(conv_id: int, patch: dict[str, Any] = Body(...)):
    not_busy(conv_id)  # the turn in progress would overwrite the change
    state = normalize_state(deep_merge(svc().conversations.get_state(conv_id), patch))
    svc().conversations.save_state(conv_id, state)
    return state


# --------------------------------------------------------------------------- NPCs
@app.get("/api/conversations/{conv_id}/npcs")
async def list_npcs(conv_id: int):
    return svc().conversations.list_npcs(conv_id)


@app.post("/api/conversations/{conv_id}/npcs")
async def create_npc(conv_id: int, body: dict[str, Any] = Body(...)):
    name = str(body.get("name", "")).strip()
    if not name:
        raise ValueError("NPC needs a name.")
    return svc().conversations.add_npc(
        conv_id, name, description=body.get("description", ""), personality=body.get("personality", ""),
        speech_style=body.get("speech_style", ""), relationship=int(body.get("relationship", 0)), notes=body.get("notes", ""),
        appearance=body.get("appearance"),
    )


@app.patch("/api/npcs/{npc_id}")
async def update_npc(npc_id: int, body: dict[str, Any] = Body(...)):
    return svc().conversations.update_npc(npc_id, **body)


@app.delete("/api/npcs/{npc_id}")
async def delete_npc(npc_id: int):
    svc().conversations.delete_npc(npc_id)
    return {"deleted": True}


# ------------------------------------------------------------------------ memory
@app.get("/api/conversations/{conv_id}/memories")
async def list_memories(conv_id: int, limit: int = 200, offset: int = 0):
    return svc().memory.list(conv_id, limit, offset)


@app.post("/api/conversations/{conv_id}/memories")
async def add_memory(conv_id: int, body: dict[str, Any] = Body(...)):
    mem_id = await svc().memory.add(conv_id, str(body.get("text", "")), kind="manual", importance=int(body.get("importance", 4)))
    if mem_id is None:
        raise ValueError("Memory text is too short or already exists.")
    return {"id": mem_id}


@app.get("/api/conversations/{conv_id}/memories/search")
async def search_memories(conv_id: int, q: str = Query(...), k: int = 8):
    return await svc().memory.search(conv_id, q, k)


@app.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: int):
    svc().memory.delete(memory_id)
    return {"deleted": True}


@app.post("/api/memories/reindex")
async def reindex_memories():
    return {"embedded": await svc().memory.reindex()}


# -------------------------------------------------------------------------- dice
@app.post("/api/dice/roll")
async def roll_dice(body: dict[str, Any] = Body(...)):
    return svc().dice.roll(str(body.get("expression", "1d20"))).to_dict()


# ------------------------------------------------------------------------ skills
@app.get("/api/skills")
async def list_skills():
    return svc().skills.list()


@app.post("/api/skills/rescan")
async def rescan_skills():
    return {"count": svc().skills.scan(), "skills": svc().skills.list()}


@app.post("/api/skills/install")
async def install_skill(body: dict[str, Any] = Body(...)):
    """Install from a local folder/zip path or a GitHub / .zip URL."""
    source = str(body.get("source", "")).strip()
    if not source:
        raise SkillError("Give a folder path, GitHub link or .zip link.")
    if source.lower().startswith(("http://", "https://")):
        names = await svc().skills.install_from_url(source)
    else:
        names = svc().skills.install_from_path(source)
    return {"installed": names, "skills": svc().skills.list()}


@app.post("/api/skills/install-zip")
async def install_skill_zip(request: Request):
    """Upload a .zip as the raw request body (Content-Type: application/zip)."""
    names = svc().skills.install_from_zip_bytes(await read_body(request, "skills"), "zip upload")
    return {"installed": names, "skills": svc().skills.list()}


@app.post("/api/skills/suggest")
async def suggest_skills(body: dict[str, Any] = Body(...)):
    """Ask the model, one time, which installed skills fit a card (it never runs during play)."""
    return await svc().skills.suggest(str(body.get("text", "")), int(body.get("k", 3)))


@app.patch("/api/skills/{name}")
async def toggle_skill(name: str, body: dict[str, Any] = Body(...)):
    svc().skills.set_enabled(name, bool(body.get("enabled", True)))
    return svc().skills.list()


@app.delete("/api/skills/{name}")
async def delete_skill(name: str):
    svc().skills.uninstall(name)
    return svc().skills.list()


# ------------------------------------------------------------------ built-in AI engine
@app.get("/api/engine")
async def engine_status():
    return svc().runtime.status()


@app.get("/api/engine/models")
async def engine_models():
    """Model pickers in Settings: every model that is not deactivated in the Models window."""
    return [m for m in await asyncio.to_thread(svc().models.local) if not m["disabled"]]


@app.post("/api/engine/start")
async def engine_start():
    if svc().settings.get("ai_engine") != "builtin":
        raise HTTPException(status_code=400, detail="Switch the AI engine to 'Built-in' first.")
    background(svc().runtime.start())
    return svc().runtime.status()


@app.post("/api/engine/stop")
async def engine_stop():
    await svc().runtime.stop()
    return svc().runtime.status()


@app.post("/api/engine/download")
async def engine_download():
    return _start_engine_download()


def _start_engine_download() -> dict:
    """Download the built-in engine in the background, then start it if a model is chosen."""
    rt = svc().runtime
    if rt.state == "downloading":
        return rt.status()

    async def run():
        try:
            await rt.download()
            if svc().settings.get("ai_engine") == "builtin":
                await rt.start()
        except EngineError:
            pass  # the status shows the reason

    rt.state, rt.message, rt.progress = "downloading", "Starting the download…", 0.0
    background(run())
    return rt.status()


# ------------------------------------------------------------------ Models window
@app.get("/api/models/library")
async def models_local():
    return {"models": await asyncio.to_thread(svc().models.local), "downloads": svc().models.list_downloads(),
            "engine": svc().runtime.status(with_log=False), "folder": str(download_root()),
            "folders": await asyncio.to_thread(svc().models.folders)}


_PICKER = asyncio.Lock()


@app.post("/api/models/folders")
async def models_add_folder(body: dict = Body(...)):
    """Use models that are already on this PC (e.g. LM Studio's) without downloading them again."""
    added = await asyncio.to_thread(svc().models.add_folder, str(body.get("path", "")))
    return {"added": added, **(await models_local())}


@app.post("/api/models/folders/remove")
async def models_remove_folder(body: dict = Body(...)):
    svc().models.remove_folder(str(body.get("path", "")))
    return await models_local()


@app.post("/api/models/browse")
async def models_browse():
    """Opens Windows' file picker on this PC; the folder of the chosen model is added."""
    if _PICKER.locked():
        raise HTTPException(409, "The file picker is already open (it may be behind this window).")
    async with _PICKER:
        picked = await asyncio.to_thread(pick_model_file)
    if not picked:
        return {"added": "", **(await models_local())}
    return await models_add_folder({"path": picked})


@app.get("/api/models/search")
async def models_search(q: str = ""):
    return await svc().models.search(q)


@app.get("/api/models/files")
async def models_files(repo: str):
    return await svc().models.files(repo)


@app.post("/api/models/download")
async def models_download(body: dict = Body(...)):
    return svc().models.start_download(str(body.get("repo", "")), str(body.get("file", "")))


@app.post("/api/models/download/cancel")
async def models_download_cancel(body: dict = Body(...)):
    svc().models.cancel(str(body.get("key", "")))
    return svc().models.list_downloads()


@app.post("/api/models/download/clear")
async def models_download_clear(body: dict = Body(...)):
    svc().models.forget(str(body.get("key", "")))
    return svc().models.list_downloads()


@app.post("/api/models/load")
async def models_load(body: dict = Body(...)):
    values = svc().models.load_values(str(body.get("path", "")), str(body.get("role", "story")))
    if not runtime_binary():  # first time: get the engine (about 30 MB), then the model loads by itself
        svc().settings.update(values)
        return _start_engine_download()
    if svc().settings.get("ai_engine") == "builtin" and all(svc().settings.get(k) == v for k, v in values.items()):
        background(svc().runtime.start())  # same model: just (re)start it
    apply_settings(values)
    return svc().runtime.status(with_log=False)


@app.post("/api/models/unload")
async def models_unload(body: dict = Body(...)):
    if str(body.get("role", "story")) == "embedding":
        apply_settings({"engine_embedding_path": ""})
    else:
        await svc().runtime.stop()
    return svc().runtime.status(with_log=False)


@app.post("/api/models/active")
async def models_active(body: dict = Body(...)):
    svc().models.set_disabled(str(body.get("path", "")), not bool(body.get("active", True)))
    return await asyncio.to_thread(svc().models.local)


@app.post("/api/models/delete")
async def models_delete(body: dict = Body(...)):
    await svc().models.delete(str(body.get("path", "")))
    return await asyncio.to_thread(svc().models.local)


# ------------------------------------------------------------------ the interface
# After the interface is built (Play.bat does it), the backend serves it too, so one address does everything.


@app.get("/{path:path}", include_in_schema=False)
async def interface(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        return JSONResponse({"detail": "The interface is not built yet. Run Play.bat (or build-frontend.bat)."}, status_code=404)
    target = (FRONTEND_DIST / path).resolve()
    if path and target.is_file() and FRONTEND_DIST.resolve() in target.parents:
        cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
        return FileResponse(target, headers={"Cache-Control": cache})
    return FileResponse(index, headers={"Cache-Control": "no-cache"})  # the app handles its own pages

