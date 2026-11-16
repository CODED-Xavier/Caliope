"""Run from the backend folder:  python -m unittest discover -s tests -v"""
import io
import json
import random
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.config import SEED_DIR
from app.dice import DiceError, DiceRoller
from app.engine import BusyError
from app.llm import LLMError, ThinkFilter, strip_think
from app.prompts import PromptBuilder
from app.services import Services
from app.state import apply_state_updates, new_state, normalize_updates
from app.util import extract_json, tokenize

SAMPLE_SKILLS = {
    "combat-encounters": """---
name: combat-encounters
description: Run fair, exciting turn-based combat: attack, fight, battle, initiative, enemies, damage, weapons, spells, ambush and flee.
---

# Combat encounters

When a fight starts:
1. Describe the scene and enemies briefly.
2. Ask the player to roll initiative (d20 + DEX modifier).
3. Resolve attacks by asking for an attack roll and comparing it with the target's AC.
""",
    "npc-dialogue-voices": """---
name: npc-dialogue-voices
description: Give every NPC a distinct voice in conversation, talk, persuade, negotiate, interrogate, flirt, bargain, shop or befriend characters.
---

# NPC dialogue and voices

- Give each NPC one verbal habit and keep it every time they speak.
- NPCs have goals. They answer what they want to answer.
- When the player persuades, deceives or intimidates, ask for a Charisma-based roll.
""",
}


class FakeLLM:
    """Stands in for LM Studio."""

    def __init__(self):
        self.reply = "The innkeeper slides a mug across the bar and studies you."
        self.analysis = {}
        self.summary = "Summary of earlier events."
        self.embeddings = False
        self.fail_stream = False
        self.stream_calls = []

    async def stream_chat(self, messages, stop=None, **kw):
        self.stream_calls.append(messages)
        if self.fail_stream:
            raise LLMError("server down")
        for word in self.reply.split(" "):
            yield word + " "

    async def chat(self, messages, json_schema=None, **kw):
        if json_schema:
            return "```json\n" + json.dumps(self.analysis) + "\n```"
        return self.summary

    async def embed(self, texts):
        if not self.embeddings:
            return None
        out = []
        for t in texts:
            v = [0.0] * 64
            for tok in tokenize(t):
                v[hash(tok) % 64] += 1.0
            out.append(v)
        return out


def make_services(llm=None, skills_src=True):
    """Fresh in-memory app. Skills come from SAMPLE_SKILLS above, never from your real backend/skills folder."""
    tmp = tempfile.mkdtemp()
    skills_dir = Path(tmp) / "skills"
    skills_dir.mkdir()
    if skills_src:
        for name, text in SAMPLE_SKILLS.items():
            (skills_dir / name).mkdir()
            (skills_dir / name / "SKILL.md").write_text(text, encoding="utf-8")
    return Services(db_path=":memory:", skills_dir=skills_dir, seed_dir=SEED_DIR, llm=llm or FakeLLM())


async def collect(agen):
    return [e async for e in agen]


class DiceTests(unittest.TestCase):
    def setUp(self):
        self.d = DiceRoller(random.Random(7))

    def test_basic_and_modifier(self):
        r = self.d.roll("2d6+3")
        self.assertEqual(r.total, sum(r.terms[0]["rolls"]) + 3)
        self.assertTrue(5 <= r.total <= 15)

    def test_advantage_keeps_higher(self):
        for _ in range(50):
            r = self.d.roll("1d20+2 adv")
            rolls = r.terms[0]["rolls"]
            self.assertEqual(len(rolls), 2)
            self.assertEqual(r.terms[0]["kept"], [max(rolls)])
            self.assertEqual(r.mode, "advantage")

    def test_disadvantage_and_keep_highest(self):
        r = self.d.roll("d20 disadvantage")
        self.assertEqual(r.terms[0]["kept"], [min(r.terms[0]["rolls"])])
        r = self.d.roll("4d6kh3")
        self.assertEqual(len(r.terms[0]["kept"]), 3)
        self.assertEqual(r.total, sum(sorted(r.terms[0]["rolls"])[1:]))

    def test_natural_and_errors(self):
        r = self.d.roll("d20")
        self.assertEqual(r.natural, r.total)
        self.assertEqual(self.d.roll("d%").terms[0]["sides"], 100)
        for bad in ("", "abc", "2d", "1d1", "500d6", "d20 d6"):
            with self.assertRaises(DiceError):
                self.d.roll(bad)

    def test_text_has_total(self):
        self.assertIn("**", self.d.roll("1d20+5").text)


class UtilTests(unittest.TestCase):
    def test_extract_json(self):
        self.assertEqual(extract_json('noise ```json\n{"a": {"b": "}"}}\n``` tail'), {"a": {"b": "}"}})
        self.assertIsNone(extract_json("no json here"))
        self.assertEqual(extract_json('<think>{"x":1}</think>{"y":2}'), {"y": 2})

    def test_think_filter_across_chunks(self):
        f = ThinkFilter()
        out = "".join(f.feed(c) for c in ["Hel", "lo <thi", "nk>secret</th", "ink>\n World"]) + f.flush()
        self.assertEqual(out, "Hello World")
        self.assertEqual(strip_think("<think>x</think> ok"), "ok")


class StateTests(unittest.TestCase):
    def test_updates_are_clamped(self):
        s = new_state({"hp": {"current": 10, "max": 12}, "gold": 5, "inventory": ["Torch"]})
        u = normalize_updates({
            "hp_change": "-4", "gold_change": 10,
            "inventory_add": [{"name": "Key", "qty": 1}, {"name": "Torch", "qty": 2}],
            "inventory_remove": [{"name": "Torch", "qty": 1}],
            "quests": [{"title": "Find the key", "status": "weird"}],
            "location": "Cellar", "new_locations": [{"name": "Attic", "connects_to": ["Cellar"]}],
        })
        s2, changes = apply_state_updates(s, u)
        self.assertEqual(s2["player"]["hp"]["current"], 6)
        self.assertEqual(s2["gold"], 15)
        self.assertEqual({i["name"]: i["qty"] for i in s2["inventory"]}, {"Torch": 2, "Key": 1})
        self.assertEqual(s2["quests"][0]["status"], "active")
        self.assertEqual(s2["location"], "Cellar")
        self.assertIn("Cellar", next(l for l in s2["locations"] if l["name"] == "Attic")["connections"])
        self.assertTrue(changes)
        big, _ = apply_state_updates(s2, normalize_updates({"hp_change": -999}))
        self.assertEqual(big["player"]["hp"]["current"], 0)
        self.assertEqual(s["player"]["hp"]["current"], 10)  # original untouched

    def test_garbage_input(self):
        u = normalize_updates("not a dict")
        self.assertEqual(u["hp_change"], 0)
        u = normalize_updates({"relationship_changes": [{"npc": "A", "delta": "x"}], "memories": ["ok fact here", 5]})
        self.assertEqual(u["relationship_changes"], [])
        self.assertEqual(len(u["memories"]), 1)


class RepoAndScenarioTests(unittest.TestCase):
    def test_seeds_and_all_modes(self):
        s = make_services()
        scenarios = s.scenarios.list()
        self.assertEqual({x["mode"] for x in scenarios}, {"gm_world", "gm_cast", "character"})
        for sc in scenarios:
            conv = s.conversations.create(s.scenarios.get(sc["id"]), player_name="Kai")
            full_npcs = s.conversations.list_npcs(conv["id"])
            state = s.conversations.get_state(conv["id"])
            self.assertEqual(state["player"]["name"], "Kai")
            if sc["mode"] == "character":
                self.assertTrue(full_npcs[0]["is_main"])
            if sc["mode"] == "gm_cast":
                self.assertEqual(len(full_npcs), 3)
            self.assertEqual(s.conversations.list_messages(conv["id"])[0]["meta"], {"opening": True})

    def test_seed_only_once(self):
        s = make_services()
        n = len(s.scenarios.list())
        self.assertEqual(s.scenarios.seed_defaults(SEED_DIR), 0)
        self.assertEqual(len(s.scenarios.list()), n)

    def test_npc_lookup_and_snapshot_restore(self):
        s = make_services()
        sc = s.scenarios.get(next(x["id"] for x in s.scenarios.list() if x["mode"] == "gm_cast"))
        conv = s.conversations.create(sc)
        cid = conv["id"]
        self.assertEqual(s.conversations.find_npc(cid, "captain doran hale")["name"], "Captain Doran Hale")
        self.assertEqual(s.conversations.find_npc(cid, "Doran")["name"], "Captain Doran Hale")
        snap = s.conversations.capture_snapshot(cid)
        s.conversations.add_npc(cid, "Stranger")
        doran = s.conversations.find_npc(cid, "Doran")
        s.conversations.update_npc(doran["id"], relationship=80)
        st = s.conversations.get_state(cid)
        st["gold"] = 999
        s.conversations.save_state(cid, st)
        s.conversations.restore_snapshot(cid, snap)
        self.assertIsNone(s.conversations.find_npc(cid, "Stranger"))
        self.assertEqual(s.conversations.find_npc(cid, "Doran")["relationship"], 0)
        self.assertEqual(s.conversations.get_state(cid)["gold"], 30)

    def test_relationship_clamped_in_db(self):
        s = make_services()
        conv = s.conversations.create(None)
        npc = s.conversations.add_npc(conv["id"], "Bob", relationship=500)
        self.assertEqual(npc["relationship"], 100)


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_keyword_search(self):
        s = make_services()
        cid = s.conversations.create(None)["id"]
        await s.memory.add(cid, "Captain Varro promised to protect the village of Eldmere", importance=4)
        await s.memory.add(cid, "The player found a silver key under the old bridge")
        await s.memory.add(cid, "The player found a silver key under the old bridge")  # duplicate ignored
        self.assertEqual(s.memory.count(cid), 2)
        hits = await s.memory.search(cid, "Where is that key I found by the bridge?")
        self.assertEqual(hits[0]["text"], "The player found a silver key under the old bridge")
        hits = await s.memory.search(cid, "tell me about Varro")
        self.assertIn("Varro", hits[0]["text"])
        self.assertEqual(await s.memory.search(cid, "dragons and wizards"), [])
        self.assertEqual(await s.memory.search(cid, "the of and"), [])

    async def test_semantic_and_reindex(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = s.conversations.create(None)["id"]
        await s.memory.add(cid, "The blacksmith Hilda owes the player a favor")  # stored without vector
        s.settings.update({"embedding_model": "fake-embed"})
        llm.embeddings = True
        self.assertEqual(await s.memory.reindex(), 1)
        await s.memory.add(cid, "A red dragon sleeps beneath the northern mountain")
        hits = await s.memory.search_semantic(cid, "dragon in the northern mountain")
        self.assertIn("dragon", hits[0]["text"])
        self.assertEqual(s.memory.count(cid), 2)

    async def test_conversations_are_isolated(self):
        s = make_services()
        a = s.conversations.create(None)["id"]
        b = s.conversations.create(None)["id"]
        await s.memory.add(a, "Secret password is moonflower")
        self.assertEqual(await s.memory.search(b, "password moonflower"), [])


class SkillTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_selection_and_policies(self):
        s = make_services()
        self.assertEqual({x["name"] for x in s.skills.list()}, {"combat-encounters", "npc-dialogue-voices"})
        picked = await s.skills.select("I attack the goblin and start a fight!", {"mode": "auto"})
        self.assertEqual([p["name"] for p in picked], ["combat-encounters"])
        picked = await s.skills.select("I want to persuade the merchant and negotiate a price", {"mode": "auto"})
        self.assertEqual([p["name"] for p in picked], ["npc-dialogue-voices"])
        self.assertEqual(await s.skills.select("I look at the sky and sigh", {"mode": "auto"}), [])
        self.assertEqual(await s.skills.select("attack fight", {"mode": "off"}), [])
        self.assertEqual(await s.skills.select("attack fight", {"mode": "manual"}), [])
        pinned = await s.skills.select("hello", {"mode": "manual", "pinned": ["npc-dialogue-voices"]})
        self.assertEqual(pinned[0]["reason"], "pinned")
        allowed = await s.skills.select("attack the goblin in a fight", {"mode": "auto", "allow": ["npc-dialogue-voices"]})
        self.assertEqual(allowed, [])

    async def test_works_with_no_skills(self):
        s = make_services(skills_src=False)
        self.assertEqual(s.skills.list(), [])
        self.assertEqual(await s.skills.select("attack!", {"mode": "auto"}), [])

    async def test_disable_and_uninstall(self):
        s = make_services()
        s.skills.set_enabled("combat-encounters", False)
        self.assertEqual(await s.skills.select("attack fight battle", {"mode": "auto"}), [])
        s.skills.uninstall("combat-encounters")
        self.assertEqual(len(s.skills.list()), 1)

    async def test_install_from_folder_and_zip(self):
        s = make_services(skills_src=False)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "some-repo" / "skills" / "tavern-brawls"
            repo.mkdir(parents=True)
            (repo / "SKILL.md").write_text("---\nname: tavern-brawls\ndescription: 'Bar fights: punch, chairs, bottles'\n---\nBody text", encoding="utf-8")
            self.assertEqual(s.skills.install_from_path(Path(tmp) / "some-repo"), ["tavern-brawls"])
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("pack-main/magic/SKILL.md", "---\nname: Magic Rules\ndescription: spells and casting\n---\nSpell text")
            self.assertEqual(s.skills.install_from_zip_bytes(buf.getvalue()), ["magic-rules"])
            evil = io.BytesIO()
            with zipfile.ZipFile(evil, "w") as zf:
                zf.writestr("../../evil/SKILL.md", "x")
            with self.assertRaises(ValueError):
                s.skills.install_from_zip_bytes(evil.getvalue())
            with self.assertRaises(ValueError):
                s.skills.install_from_zip_bytes(b"not a zip")
        self.assertEqual({x["name"] for x in s.skills.list()}, {"tavern-brawls", "magic-rules"})

    def test_frontmatter_fallback(self):
        from app.skills import parse_skill_md

        meta, body = parse_skill_md("---\nname: x\ndescription: has: colon: in it\n---\nHello")
        self.assertEqual(meta["name"], "x")
        self.assertEqual(body, "Hello")


class PromptTests(unittest.TestCase):
    def test_fits_context_and_alternates(self):
        s = make_services()
        sc = s.scenarios.get(next(x["id"] for x in s.scenarios.list() if x["mode"] == "gm_world"))
        conv = s.conversations.create(sc)
        cid = conv["id"]
        for i in range(60):
            s.conversations.add_message(cid, "user", f"I do thing number {i} " + "word " * 60)
            s.conversations.add_message(cid, "assistant", f"Result {i} " + "text " * 80)
        history = s.conversations.list_messages(cid)
        settings = s.settings.all() | {"context_window": 4096, "max_tokens": 600}
        msgs, debug = PromptBuilder().build(
            scenario=conv["scenario"], state=s.conversations.get_state(cid), npcs=[], summary="Earlier things happened.",
            memories=[{"text": "A fact", "message_id": None}], skills=[], history=history, settings=settings)
        total = sum(len(m["content"]) for m in msgs) / 3.4
        self.assertLess(total, 4096 - 600)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[1]["role"], "user")
        roles = [m["role"] for m in msgs[1:]]
        self.assertTrue(all(a != b for a, b in zip(roles, roles[1:])))
        self.assertGreater(debug["trimmed_messages"], 0)
        self.assertIn("Earlier things happened.", msgs[0]["content"])
        self.assertIn("Opening scene", msgs[0]["content"])  # opening goes into the system prompt

    def test_character_mode_prompt(self):
        s = make_services()
        sc = s.scenarios.get(next(x["id"] for x in s.scenarios.list() if x["mode"] == "character"))
        conv = s.conversations.create(sc)
        msgs, _ = PromptBuilder().build(
            scenario=conv["scenario"], state=s.conversations.get_state(conv["id"]),
            npcs=s.conversations.list_npcs(conv["id"]), summary="", memories=[], skills=[],
            history=[{"id": 1, "role": "user", "content": "Hi", "meta": {}}], settings=s.settings.all())
        self.assertIn("roleplaying as Mira", msgs[0]["content"])
        self.assertIn("relationship +0, neutral", msgs[0]["content"])
        self.assertNotIn("Game Master", msgs[0]["content"])


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def start(self, mode="gm_world", **llm_attrs):
        llm = FakeLLM()
        for k, v in llm_attrs.items():
            setattr(llm, k, v)
        s = make_services(llm)
        sc = s.scenarios.get(next(x["id"] for x in s.scenarios.list() if x["mode"] == mode))
        cid = s.conversations.create(sc)["id"]
        return s, llm, cid

    async def test_full_turn(self):
        s, llm, cid = await self.start(
            "gm_cast",
            analysis={
                "hp_change": -3, "gold_change": -5, "inventory_add": [{"name": "Ale", "qty": 1}],
                "relationship_changes": [{"npc": "Doran", "delta": 50, "reason": "shared a drink"}],
                "new_npcs": [{"name": "Old Tom", "description": "A drunk", "personality": "Chatty"}],
                "memories": [{"text": "Captain Doran Hale shared a drink with the investigator", "importance": 4}],
                "location": "The Barracks",
            })
        events = await collect(s.engine.send(cid, "I attack the guard captain"))
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "user_message")
        self.assertIn("context", types)
        self.assertEqual("".join(e["text"] for e in events if e["type"] == "token").strip(), llm.reply)
        self.assertEqual(types[-1], "done")
        st = next(e for e in events if e["type"] == "state")
        self.assertEqual(st["state"]["player"]["hp"]["current"], 7)
        self.assertEqual(st["state"]["gold"], 25)
        doran = s.conversations.find_npc(cid, "Doran")
        self.assertEqual(doran["relationship"], 20)  # clamped to max step
        self.assertIsNotNone(s.conversations.find_npc(cid, "Old Tom"))
        self.assertEqual(await s.memory.search(cid, "Doran drink"), await s.memory.search(cid, "Doran drink"))
        self.assertTrue(any("Doran" in m["text"] for m in await s.memory.search(cid, "Doran drink")))
        ctx = next(e for e in events if e["type"] == "context")
        self.assertEqual(ctx["skills"], ["combat-encounters"])  # auto-picked from "attack"
        system_prompt = llm.stream_calls[0][0]["content"]
        self.assertIn("Reference material", system_prompt)
        self.assertIn("Captain Doran Hale", system_prompt)
        msgs = s.conversations.list_messages(cid)
        self.assertEqual([m["role"] for m in msgs], ["assistant", "user", "assistant"])
        self.assertNotIn("snapshot", msgs[-1]["meta"])
        self.assertTrue(msgs[-1]["meta"]["changes"])
        self.assertIn("attack", s.conversations.get(cid)["title"].lower())

    async def test_roll_command(self):
        s, llm, cid = await self.start()
        events = await collect(s.engine.send(cid, "/roll 1d20+5 adv"))
        self.assertEqual(events[0]["type"], "dice")
        user = next(e for e in events if e["type"] == "user_message")["message"]
        self.assertTrue(user["content"].startswith("\U0001F3B2"))
        events = await collect(s.engine.send(cid, "/roll banana"))
        self.assertEqual(events[0]["type"], "error")

    async def test_regenerate_restores_state(self):
        s, llm, cid = await self.start(analysis={"gold_change": 40, "memories": [{"text": "The player found a purse of gold coins", "importance": 3}]})
        await collect(s.engine.send(cid, "I search the room"))
        self.assertEqual(s.conversations.get_state(cid)["gold"], 55)
        self.assertEqual(s.memory.count(cid), 1)
        llm.reply = "A different narration."
        events = await collect(s.engine.regenerate(cid))
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(s.conversations.get_state(cid)["gold"], 55)  # not double-applied
        self.assertEqual(s.memory.count(cid), 1)
        msgs = s.conversations.list_messages(cid)
        self.assertEqual([m["role"] for m in msgs], ["assistant", "user", "assistant"])
        self.assertEqual(msgs[-1]["content"], "A different narration.")

    async def test_undo(self):
        s, llm, cid = await self.start(analysis={"gold_change": 10})
        await collect(s.engine.send(cid, "I look around"))
        self.assertEqual(s.engine.undo(cid)["removed"], 2)
        self.assertEqual(s.conversations.get_state(cid)["gold"], 15)
        self.assertEqual(len(s.conversations.list_messages(cid)), 1)
        self.assertEqual(s.engine.undo(cid)["removed"], 0)  # opening scene is protected

    async def test_character_mode_tracks_relationship_only(self):
        s, llm, cid = await self.start(
            "character", analysis={"hp_change": -9, "relationship_changes": [{"npc": "somebody else", "delta": 7, "reason": "kind words"}]})
        await collect(s.engine.send(cid, "Thank you for the stew, Mira."))
        self.assertEqual(s.conversations.find_npc(cid, "Mira")["relationship"], 7)
        self.assertEqual(s.conversations.get_state(cid)["player"]["hp"]["current"], 10)

    async def test_llm_failure_and_bad_analysis(self):
        s, llm, cid = await self.start(fail_stream=True)
        events = await collect(s.engine.send(cid, "Hello?"))
        self.assertEqual(events[-1]["type"], "error")
        llm.fail_stream = False
        llm.analysis = None  # model returns "null" -> no usable JSON
        events = await collect(s.engine.send(cid, "Hello again"))
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(s.memory.count(cid), 1)  # fallback exchange memory
        self.assertTrue(any(m["kind"] == "exchange" for m in s.memory.list(cid)))

    async def test_state_tracking_off(self):
        s, llm, cid = await self.start()
        s.settings.update({"state_tracking": False})
        events = await collect(s.engine.send(cid, "I wave"))
        self.assertNotIn("analysis_start", [e["type"] for e in events])
        self.assertEqual(s.memory.count(cid), 1)

    async def test_auto_summary_triggers(self):
        s, llm, cid = await self.start()
        s.settings.update({"state_tracking": False, "context_window": 2048, "max_tokens": 300, "keep_recent_messages": 4})
        llm.reply = "Long narration " + "words " * 150
        summarized = False
        for i in range(8):
            events = await collect(s.engine.send(cid, f"Action {i} " + "detail " * 40))
            summarized = summarized or any(e["type"] == "summary" for e in events)
        self.assertTrue(summarized)
        conv = s.conversations.get(cid)
        self.assertEqual(conv["summary"], llm.summary)
        self.assertGreater(conv["summary_upto"], 0)
        last_prompt = llm.stream_calls[-1]
        self.assertIn(llm.summary, last_prompt[0]["content"])
        full = s.conversations.list_messages(cid)
        self.assertEqual(len(full), 1 + 16)  # full history is never deleted

    async def test_busy_conversation_rejected(self):
        s, llm, cid = await self.start()
        await s.engine._lock(cid).acquire()
        events = await collect(s.engine.send(cid, "hi"))
        self.assertEqual(events[0]["type"], "error")

    async def test_cancelled_stream_keeps_partial(self):
        s, llm, cid = await self.start()
        agen = s.engine.send(cid, "Tell me a long story")
        async for e in agen:
            if e["type"] == "token":
                break
        await agen.aclose()
        msgs = s.conversations.list_messages(cid)
        self.assertEqual(msgs[-1]["role"], "assistant")
        self.assertTrue(msgs[-1]["meta"].get("interrupted"))


class HistoryEditTests(unittest.IsolatedAsyncioTestCase):
    async def start(self, **llm_attrs):
        llm = FakeLLM()
        for k, v in llm_attrs.items():
            setattr(llm, k, v)
        s = make_services(llm)
        sc = s.scenarios.get(next(x["id"] for x in s.scenarios.list() if x["mode"] == "gm_world"))
        return s, llm, s.conversations.create(sc)["id"]

    async def test_edit_in_place(self):
        s, llm, cid = await self.start()
        await collect(s.engine.send(cid, "hello there"))
        msgs = s.conversations.list_messages(cid)
        edited = s.engine.edit_message(msgs[2]["id"], "  A rewritten reply.  ")
        self.assertEqual(edited["content"], "A rewritten reply.")
        self.assertTrue(edited["meta"]["edited"])
        self.assertNotIn("snapshot", edited["meta"])
        # snapshot (needed for regenerate) survived the edit
        self.assertIsNotNone(s.conversations.get_message(msgs[2]["id"], with_snapshot=True)["snapshot"])
        with self.assertRaises(ValueError):
            s.engine.edit_message(msgs[2]["id"], "   ")
        await s.engine._lock(cid).acquire()
        with self.assertRaises(BusyError):
            s.engine.edit_message(msgs[2]["id"], "x")

    async def test_rewind_keeps_or_removes_selected_message(self):
        s, llm, cid = await self.start(analysis={"gold_change": 10, "memories": [{"text": "Something memorable happened here", "importance": 3}]})
        await collect(s.engine.send(cid, "turn one"))
        llm.analysis = {"gold_change": 10, "memories": [{"text": "A different memorable event later", "importance": 3}]}
        await collect(s.engine.send(cid, "turn two"))
        self.assertEqual(s.conversations.get_state(cid)["gold"], 35)
        msgs = s.conversations.list_messages(cid)
        self.assertEqual(len(msgs), 5)
        # keep the first reply, remove turn two
        self.assertEqual(s.engine.rewind(cid, msgs[2]["id"], inclusive=False)["removed"], 2)
        self.assertEqual(s.conversations.get_state(cid)["gold"], 25)
        self.assertEqual([m["text"] for m in s.memory.list(cid)], ["Something memorable happened here"])
        self.assertEqual(len(s.conversations.list_messages(cid)), 3)
        # delete turn one entirely, including the selected message
        self.assertEqual(s.engine.rewind(cid, msgs[1]["id"], inclusive=True)["removed"], 2)
        self.assertEqual(s.conversations.get_state(cid)["gold"], 15)
        self.assertEqual(s.memory.count(cid), 0)
        self.assertEqual(len(s.conversations.list_messages(cid)), 1)
        with self.assertRaises(ValueError):
            s.engine.rewind(cid, msgs[0]["id"], inclusive=True)  # opening scene is protected
        self.assertEqual(s.engine.rewind(cid, msgs[0]["id"], inclusive=False)["removed"], 0)

    async def test_rewind_discards_summary_that_covered_removed_text(self):
        s, llm, cid = await self.start()
        await collect(s.engine.send(cid, "one"))
        await collect(s.engine.send(cid, "two"))
        msgs = s.conversations.list_messages(cid)
        s.conversations.set_summary(cid, "An old summary", msgs[3]["id"])
        s.engine.rewind(cid, msgs[2]["id"], inclusive=False)
        conv = s.conversations.get(cid)
        self.assertEqual((conv["summary"], conv["summary_upto"]), ("", 0))

    async def test_resend_edited_message(self):
        s, llm, cid = await self.start(analysis={"gold_change": 10})
        await collect(s.engine.send(cid, "first"))
        await collect(s.engine.send(cid, "second"))
        self.assertEqual(s.conversations.get_state(cid)["gold"], 35)
        first_user = s.conversations.list_messages(cid)[1]
        llm.reply = "A fresh answer."
        llm.analysis = {"gold_change": 3}
        events = await collect(s.engine.resend(cid, first_user["id"], "first, but edited"))
        self.assertEqual(events[0]["type"], "rolled_back")
        self.assertEqual(events[-1]["type"], "done")
        msgs = s.conversations.list_messages(cid)
        self.assertEqual([m["role"] for m in msgs], ["assistant", "user", "assistant"])
        self.assertEqual(msgs[1]["content"], "first, but edited")
        self.assertTrue(msgs[1]["meta"]["edited"])
        self.assertEqual(msgs[2]["content"], "A fresh answer.")
        self.assertEqual(s.conversations.get_state(cid)["gold"], 18)  # 15 + 3, turn two undone
        self.assertEqual(s.memory.count(cid), 1)
        last_prompt = llm.stream_calls[-1]
        self.assertEqual(last_prompt[-1]["content"], "first, but edited")
        self.assertNotIn("second", json.dumps(last_prompt))

    async def test_resend_rejects_wrong_targets(self):
        s, llm, cid = await self.start()
        await collect(s.engine.send(cid, "hi"))
        msgs = s.conversations.list_messages(cid)
        events = await collect(s.engine.resend(cid, msgs[2]["id"], "x"))  # an assistant message
        self.assertEqual(events[0]["type"], "error")
        events = await collect(s.engine.resend(cid, msgs[1]["id"], "  "))
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(len(s.conversations.list_messages(cid)), 3)  # nothing was destroyed


if __name__ == "__main__":
    unittest.main()