"""Paths and user-editable settings (stored in the database, editable from the UI)."""
from __future__ import annotations

import json
from pathlib import Path

from .db import Database

BASE_DIR = Path(__file__).resolve().parent.parent  # the backend/ folder
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "rpg.db"
SKILLS_DIR = BASE_DIR / "skills"
SEED_DIR = Path(__file__).resolve().parent / "seed"

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
    "context_window": 8192,   # must match the context length loaded in LM Studio
    # --- Behaviour ---
    "response_language": "en",     # "en", "pt-BR" or "auto"
    "extra_instructions": "",      # appended to every system prompt
    "state_tracking": True,        # extra model call after each turn to update HP/gold/relationships/memories
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
    # --- Skills ---
    "skills_top_k": 2,
    "skills_min_score": 0.6,        # keyword matching threshold
    "skills_min_similarity": 0.45,  # embedding matching threshold
    "skills_char_budget": 3500,     # max characters of skill text injected per turn
}


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
        if isinstance(default, bool):
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if isinstance(default, int):
            return int(value)
        if isinstance(default, float):
            return float(value)
        return "" if value is None else str(value)
