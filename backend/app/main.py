"""FastAPI app. Run with:  python run.py   (API docs at http://localhost:8000/docs)"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import aclosing, asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR
from .conversations import NotFound
from .dice import DiceError
from .engine import BusyError
from .llm import LLMError
from .scenarios import generate_scenario
from .services import Services
from .skills import SkillError
from .state import normalize_state
from .util import deep_merge

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.svc = Services()
    yield
    await app.state.svc.close()


app = FastAPI(title="Local RPG Chat", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def svc() -> Services:
    return app.state.svc


@app.exception_handler(NotFound)
async def _not_found(_: Request, exc: NotFound):
    return JSONResponse({"detail": str(exc)}, status_code=404)


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
    return {"backend": "ok", "llm": await svc().llm.health(), "skills": len(svc().skills.list())}


@app.get("/api/models")
async def models():
    return {"models": await svc().llm.list_models()}


# ----------------------------------------------------------------------- settings
@app.get("/api/settings")
async def get_settings():
    return svc().settings.all()


@app.put("/api/settings")
async def put_settings(values: dict[str, Any] = Body(...)):
    return svc().settings.update(values)


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
    data = await generate_scenario(svc().llm, idea, body.get("mode", "gm_world"), body.get("language", "en"))
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
    conv = svc().conversations.create(scenario, title=str(body.get("title", "")), player_name=body.get("player_name"))
    return full_conversation(conv["id"])


def full_conversation(conv_id: int) -> dict:
    s = svc()
    return {
        "conversation": s.conversations.get(conv_id),
        "messages": s.conversations.list_messages(conv_id),
        "state": s.conversations.get_state(conv_id),
        "npcs": s.conversations.list_npcs(conv_id),
        "memory_count": s.memory.count(conv_id),
        "pinned_limit": int(s.settings.get("pinned_memory_limit")),
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


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: int):
    svc().conversations.delete(conv_id)
    return {"deleted": True}


@app.post("/api/conversations/{conv_id}/chat")
async def chat(conv_id: int, body: dict[str, Any] = Body(...)):
    svc().conversations.get(conv_id)
    return stream_response(svc().engine.send(conv_id, str(body.get("content", ""))))


@app.post("/api/conversations/{conv_id}/regenerate")
async def regenerate(conv_id: int):
    svc().conversations.get(conv_id)
    return stream_response(svc().engine.regenerate(conv_id))


@app.post("/api/conversations/{conv_id}/undo")
async def undo(conv_id: int):
    svc().conversations.get(conv_id)
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
    names = svc().skills.install_from_zip_bytes(await request.body(), "zip upload")
    return {"installed": names, "skills": svc().skills.list()}


@app.get("/api/skills/select")
async def preview_skill_selection(q: str = Query(...)):
    """Debug helper: which skills would be injected for this message?"""
    picked = await svc().skills.select(q, {"mode": "auto"})
    return [{k: v for k, v in s.items() if k != "text"} for s in picked]


@app.patch("/api/skills/{name}")
async def toggle_skill(name: str, body: dict[str, Any] = Body(...)):
    svc().skills.set_enabled(name, bool(body.get("enabled", True)))
    return svc().skills.list()


@app.delete("/api/skills/{name}")
async def delete_skill(name: str):
    svc().skills.uninstall(name)
    return svc().skills.list()


# ------------------------------------------------------- built frontend (optional)
# After `npm run build` in the frontend folder, the app is served at http://127.0.0.1:8000/
_DIST = BASE_DIR.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="web")
