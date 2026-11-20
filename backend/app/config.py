"""Paths and user-editable settings (stored in the database, editable from the UI)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .db import Database

# Two ways to run: from the source folder (Play.bat), or as the Windows program (Caliope.exe, built by
# build-exe.bat). The program keeps its read-only parts inside its _internal folder and your saves next to it.
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    APP_HOME = Path(sys.executable).resolve().parent         # the folder that holds Caliope.exe
    _BUNDLE = Path(getattr(sys, "_MEIPASS", APP_HOME))
    BASE_DIR = APP_HOME
    SEED_DIR = _BUNDLE / "app" / "seed"
    FRONTEND_DIST = _BUNDLE / "frontend_dist"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent       # the backend/ folder
    APP_HOME = BASE_DIR.parent                              # the project folder
    SEED_DIR = Path(__file__).resolve().parent / "seed"
    FRONTEND_DIST = APP_HOME / "frontend" / "dist"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "rpg.db"
SKILLS_DIR = BASE_DIR / "skills"

DEFAULT_SETTINGS: dict = {
    # --- Connection to the local model server (LM Studio by default) ---
    "llm_base_url": "http://localhost:1234/v1",
    "api_key": "lm-studio",
    "model": "",              # blank = first model the server reports
    "embedding_model": "",    # blank = no embeddings (keyword memory search only)
    # --- Generation ---
    "temperature": 0.85,
    "top_p": 0.95,
    "top_k": 40,
    "min_p": 0.05,
    "repeat_penalty": 1.08,
    "max_tokens": 800,            # hard cap for one reply (the "Reply length" setting is usually lower)
    "reply_length": "medium",     # short | medium | long
    "context_window": 8192,   # must match the context length loaded in LM Studio (the built-in engine uses it directly)
    # --- AI engine: LM Studio (default) or the built-in llama.cpp engine ---
    "ai_engine": "lmstudio",      # lmstudio | builtin
    "engine_model_path": "",      # .gguf file for the story model
    "model_folders": "",          # extra folders with .gguf models (one per line), added in the Models window
    "engine_embedding_path": "",  # optional .gguf embedding model (memory search by meaning)
    "engine_port": 8091,
    "engine_gpu_layers": "auto",  # auto | all | a number (lower it when video memory runs out)
    # --- Behaviour ---
    "response_language": "en",     # "en", "pt-BR" or "auto"
    "extra_instructions": "",      # appended to every system prompt
    "state_tracking": True,        # extra model call after each turn to update HP/gold/relationships/memories
    "tracker_skip": True,          # skip that call on quiet turns (pure talk); it reads them later
    "relationship_max_step": 20,   # max relationship change per turn
    # --- Memory ---
    "auto_summary": True,
    "recent_rounds": 10,          # rounds (player message + reply) kept word for word
    "fold_block_rounds": 5,       # when full, this many of the oldest rounds are folded into the summary at once
    "pinned_memory_limit": 2000,  # characters in the "remember this" box
    "summary_char_budget": 1500,
    "memory_top_k": 5,
    "memory_char_budget": 900,    # characters of recalled facts added to each turn
    "memory_min_similarity": 0.40,
    "show_timing": True,
    "chars_per_token": 3.4,
    "app_window": True,           # Play.bat / Caliope.exe open the game in its own window instead of a browser tab       # measured automatically from the model server's real token counts
    # --- Cards and skills ---
    "default_card_kind": "roleplay",  # type used for new cards: roleplay | adventure
    "skills_char_budget": 3500,       # max characters of attached skill text shared by one card's skills
    # --- Rulebooks ---
    "rules_char_budget": 1400,        # characters of rulebook passages added to a turn (about 350 tokens)
    # --- Scene pictures (optional, uses the free Pollinations.ai service over the internet) ---
    "scene_pictures": False,
    "picture_service": "pollinations",  # pollinations (free, no account) | pixai (your own API key)
    "pixai_api_key": "",
    "pixai_model": "",            # PixAI model version ID
    # --- Cloudflare R2 (optional private cloud storage for card pictures) ---
    "r2_account_id": "",
    "r2_bucket": "",
    "r2_access_key_id": "",
    "r2_secret_access_key": "",
    "scene_picture_style": "atmospheric fantasy painting, detailed, cinematic lighting",
}


def embedding_key(settings: dict) -> str:
    """Name of the embedding model in use ('' = none). Stored vectors are tagged with it, so a different model
    re-embeds instead of mixing incompatible vectors."""
    if settings.get("ai_engine") == "builtin":
        path = settings.get("engine_embedding_path") or ""
        return "gguf:" + Path(path).stem if path else ""
    return settings.get("embedding_model") or ""


class SettingsStore:
    """Defaults merged with whatever the user saved."""

    def __init__(self, db: Database):
        self.db = db
        self._cache: dict | None = None

    def all(self) -> dict:
        if self._cache is None:
            merged = dict(DEFAULT_SETTINGS)
            for row in self.db.query("SELECT key, value FROM settings"):
                if row["key"] in DEFAULT_SETTINGS:
                    try:
                        merged[row["key"]] = self._coerce(row["key"], json.loads(row["value"]))
                    except (ValueError, TypeError):
                        pass
            self._cache = merged
        return dict(self._cache)

    def get(self, key: str):
        return self.all()[key]

    def update(self, values: dict) -> dict:
        with self.db.transaction():
            for key, value in values.items():
                if key not in DEFAULT_SETTINGS:
                    raise ValueError(f"Unknown setting: {key}")
                coerced = self._coerce(key, value)
                self.db.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(coerced)),
                )
        self._cache = None
        return self.all()

    def reset(self) -> dict:
        self.db.execute("DELETE FROM settings")
        self._cache = None
        return self.all()

    @staticmethod
    def _coerce(key: str, value):
        default = DEFAULT_SETTINGS[key]
        if key == "picture_service" and value not in ("pollinations", "pixai"):
            raise ValueError("picture_service must be 'pollinations' or 'pixai'")
        if key == "ai_engine" and value not in ("lmstudio", "builtin"):
            raise ValueError("ai_engine must be 'lmstudio' or 'builtin'")
        if key == "engine_gpu_layers":
            value = str(value).strip().lower() or "auto"
            if value not in ("auto", "all") and not value.isdigit():
                raise ValueError("GPU layers must be auto, all or a number")
            return value
        if key == "engine_port" and not 1024 <= int(value) <= 65000:
            raise ValueError("The engine port must be between 1024 and 65000")
        if isinstance(default, bool):
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if isinstance(default, int):
            return int(value)
        if isinstance(default, float):
            return float(value)
        return "" if value is None else str(value)
