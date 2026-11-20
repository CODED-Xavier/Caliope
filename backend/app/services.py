"""Creates and wires every component. Used by the API and by the tests."""
from __future__ import annotations

from pathlib import Path

from .config import DB_PATH, SEED_DIR, SKILLS_DIR, SettingsStore
from .conversations import ConversationRepository
from .db import Database
from .dice import DiceRoller
from .engine import ChatEngine
from .llm import LLMClient
from .combat import CombatEngine
from .maps import MapRepository
from .memory import MemoryManager
from .rulebooks import RulebookRepository
from .scenarios import ScenarioRepository
from .skills import SkillManager


class Services:
    def __init__(self, db_path: str | Path = DB_PATH, skills_dir: str | Path = SKILLS_DIR,
                 seed_dir: str | Path = SEED_DIR, llm=None):
        self.db = Database(db_path)
        self.settings = SettingsStore(self.db)
        self.llm = llm or LLMClient(self.settings.all)
        self.scenarios = ScenarioRepository(self.db)
        self.scenarios.seed_defaults(Path(seed_dir))
        self.conversations = ConversationRepository(self.db)
        self.memory = MemoryManager(self.db, self.llm, self.settings.all)
        self.skills = SkillManager(self.db, Path(skills_dir), self.llm, self.settings.all)
        self.dice = DiceRoller()
        self.rulebooks = RulebookRepository(self.db, self.llm, self.settings.all)
        self.combat = CombatEngine(self.dice)
        self.maps = MapRepository(self.db)
        self.engine = ChatEngine(self.conversations, self.settings, self.llm, self.memory, self.skills, self.dice,
                                 rulebooks=self.rulebooks)

    async def close(self) -> None:
        aclose = getattr(self.llm, "aclose", None)
        if aclose:
            await aclose()
        self.db.close()
