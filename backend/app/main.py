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
from .config import DB_PATH, FRONTEND_DIST
from .conversations import NotFound
from .drafts import draft_card_field, draft_player
from .exporting import export_markdown
from .combat import CombatError, player_defaults, suggest_fight
from .maps import FEATURES as MAP_FEATURES
from .maps import TILES as MAP_TILES
from .maps import TYPES as MAP_TYPES
from .maps import MapError, generate as generate_map
from .jukebox import MOODS as MUSIC_MOODS
from .jukebox import MusicError
from .rulebooks import RulebookError, ocr_available
from .runtime import ENGINE_KEYS, EngineError
from .modelhub import download_root, pick_model_file
from .picker import pick_folder
from . import backups, cardpics, r2
from .voice import CATALOG as VOICE_CATALOG, VoiceError
from .images import UPLOAD_NAME, ImageError, get_image, http_fetch, save_upload
from .scenes import PixAIError, is_pixai, is_pollinations, pixai_paint, polite_fetch
from .playerlore import parse_suggestions, suggest_prompt
from .checks import roll_line
from . import shop
from . import resources
from . import statusbook
from . import worldtime
from .dice import DiceError
from .engine import BusyError
from .llm import LLMError
from .scenarios import generate_scenario, normalize_scenario
from .services import Services
from .skills import SkillError
from .state import normalize_state
from .util import deep_merge

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.svc = Services()
    app.state.tasks = set()
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


@app.put("/api/scenarios/{scenario_id}")
async def update_scenario(scenario_id: int, data: dict[str, Any] = Body(...)):
    scenario = svc().scenarios.update(scenario_id, data)
    if not scenario:
        raise NotFound(f"Scenario {scenario_id} not found")
    return scenario


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
        prepare = lambda st: s.combat.start(st, body.get("system", "d20"), body.get("enemies") or [],  # noqa: E731
                                            body.get("allies") or [], body.get("player") or {}, body.get("grid") or {},
                                            body.get("map") if isinstance(body.get("map"), dict) else None)
    elif action == "act":
        prepare = lambda st: s.combat.player_action(st, body.get("move", "attack"), str(body.get("target", "")),  # noqa: E731
                                                    str(body.get("advantage", "")), str(body.get("ability", "")))
    elif action == "enemies":
        prepare = s.combat.enemies_act
    elif action == "end":
        prepare = lambda st: s.combat.end(st, str(body.get("reason", "")))  # noqa: E731
    else:
        raise CombatError("Unknown combat action.")
    return stream_response(s.engine.send(conv_id, str(body.get("text", "")), prepare=prepare))


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
    except Exception:
        svc().scenarios.delete(created["id"])
        raise
    return svc().scenarios.update(created["id"], {**data, "name": name})


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


@app.post("/api/conversations/{conv_id}/recap")
async def recap(conv_id: int):
    """"Previously, in…": written only when asked, never added to the story."""
    conv = svc().conversations.get(conv_id)
    language = conv["scenario"].get("language") or svc().settings.get("response_language")
    return {"text": await svc().cantos.recap(conv_id, conv["title"], conv["summary"], language)}


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


@app.post("/api/muse/{talk_id}/message")
async def muse_message(talk_id: int, body: dict = Body(...)):
    svc().muse.get(talk_id)
    return stream_response(_one_at_a_time(svc().muse.talk(talk_id, str(body.get("content", "")))))


@app.post("/api/muse/{talk_id}/card")
async def muse_card(talk_id: int):
    svc().muse.get(talk_id)
    return stream_response(_one_at_a_time(svc().muse.make_card(talk_id)))


@app.post("/api/cards/export")
async def card_to_file(body: dict = Body(...)):
    """A card the Muse made, as a standard Character Card file (without adding it to Calíope)."""
    return export_card(normalize_scenario(body.get("card") or {}))


# ------------------------------------------------------------------ a card's pictures from a folder on this PC
CARDPIC_DIR = Path(DB_PATH).parent / "cardpics"
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
    raw_over = {str(k): str(v) for k, v in (body.get("overrides") or {}).items()}
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
            path = CARDPIC_DIR / str(scenario_id) / url[len(prefix):]
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
        scenario = svc().scenarios.get(int(body["scenario_id"]))
        if not scenario:
            raise NotFound("Scenario not found")
    player = body.get("player") if isinstance(body.get("player"), dict) else None
    conv = svc().conversations.create(scenario, title=str(body.get("title", "")), player_name=body.get("player_name"),
                                      start=str(body.get("start") or ""),
                                      player=player, setup=str(body.get("setup") or ""),
                                      player_lore=body.get("player_lore") if isinstance(body.get("player_lore"), list) else None)
    return full_conversation(conv["id"])


def _card_has_resources(conv_id: int) -> bool:
    sid = svc().conversations.get(conv_id)["scenario_id"]
    card = svc().scenarios.get(sid) if sid else None
    return bool(card and card["data"].get("resources"))


def not_busy(conv_id: int) -> None:
    if svc().engine.is_busy(conv_id):
        raise BusyError("Wait for the current reply to finish.")


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
        "status_by_app": bool(s.engine._status_template(s.conversations.get(conv_id)["scenario"], s.settings.all())),
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
    svc().conversations.get(conv_id)
    return stream_response(svc().engine.send(conv_id, str(body.get("content", ""))))


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
    line = roll_line(s.dice, s.conversations.get_state(conv_id), asked[index], mode if mode in ("advantage", "disadvantage") else "")
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
    args = (int(body.get("amount", 0) or 0), str(body.get("to", "")), str(body.get("why", "")), currency)
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
    return full_conversation(svc().engine.fork(conv_id, int(body["message_id"])))


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

