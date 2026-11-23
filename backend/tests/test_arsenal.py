"""The arsenal: named techniques of the player and of the characters, remembered and sent back to the Aedo."""
import unittest

from app import arsenal
from app.state import normalize_state

NPCS = [{"name": "Lilia Valenheart", "description": "1st-Year Knight Dept, Expert (Mid). Red hair."},
        {"name": "Professor Yanagi", "description": "Head of Theology, Sanctified (Apex)."}]
SPEECH = ("*Aster points his sword at the opponent, katana at the height of his chin.*\n\n[Chou no Mai - Manabiki]\n\n"
          "*He talks softly, almost disappearing as he dashes, a single piercing strike like a bee sting.*")


class PlayerTests(unittest.TestCase):
    def test_a_bracketed_name_is_a_technique(self):
        got = arsenal.player_moves(SPEECH)
        self.assertEqual(got[0][0], "Chou no Mai - Manabiki")
        self.assertIn("bee sting", got[0][1])

    def test_commands_and_dice_are_not_techniques(self):
        for text in ("[Override: Evolve Tier]", "[OOC: brb]", "[2d6]", "[[show: Lilia | Happy]]", "[12]"):
            self.assertEqual(arsenal.player_moves(text), [], text)

    def test_the_player_keeps_it_and_uses_count(self):
        st = {"player": {"name": "Aster"}, "card_status": {"Tier": "Expert (Low)"}}
        first = arsenal.note_player(st, SPEECH)
        self.assertTrue(first[0]["new"])
        self.assertEqual(first[0]["tier"], "Expert (Low)")
        again = arsenal.note_player(st, "[Chou no Mai - Manabiki] once more!")
        self.assertFalse(again[0]["new"])
        self.assertEqual(st["arsenal"]["Aster"][0]["uses"], 2)
        self.assertIn("bee sting", st["arsenal"]["Aster"][0]["desc"])  # the first description stays


class ReplyTests(unittest.TestCase):
    def test_a_move_tag_becomes_a_call_out_and_is_kept(self):
        reply = ('Lilia grins.\n\n[[move: Lilia | Crimson Fang]]\nHer blade rises in a red arc of aura that splits the air.\n\n'
                 '"Again!"')
        st = {"player": {"name": "Aster"}}
        text, kept = arsenal.note_reply(st, reply, NPCS)
        self.assertIn("**『Crimson Fang』**", text)
        self.assertNotIn("[[move", text)
        self.assertEqual(kept[0]["owner"], "Lilia Valenheart")
        self.assertEqual(kept[0]["tier"], "Expert (Mid)")
        self.assertIn("red arc", st["arsenal"]["Lilia Valenheart"][0]["desc"])

    def test_the_aedo_never_keeps_a_move_for_the_player(self):
        st = {"player": {"name": "Aster"}}
        text, kept = arsenal.note_reply(st, "[[move: Aster | Bee Sting]]\nHe lunges.", NPCS)
        self.assertEqual(kept, [])
        self.assertIn("『Bee Sting』", text)

    def test_a_tag_without_owner_is_still_shown(self):
        text, kept = arsenal.note_reply({}, "[[move: Thunderclap]]\nBoom.", NPCS)
        self.assertIn("『Thunderclap』", text)
        self.assertEqual(kept, [])


class ListAndEditTests(unittest.TestCase):
    def state(self):
        st = {"player": {"name": "Aster"}}
        arsenal.record(st, "Aster", "Chou no Mai - Manabiki", "a bee-sting thrust", "Expert (Low)")
        arsenal.record(st, "Lilia Valenheart", "Crimson Fang", "a rising red arc", "Expert (Mid)")
        arsenal.record(st, "Professor Yanagi", "Lotus Ward", "a ring of light", "Sanctified (Apex)")
        return st

    def test_only_the_characters_here_are_listed(self):
        text = arsenal.prompt_list(self.state(), ["Lilia raises her sword."], "Aster")
        self.assertIn("Aster (the player): 『Chou no Mai - Manabiki』 (Expert (Low))", text)
        self.assertIn("Crimson Fang", text)
        self.assertNotIn("Lotus Ward", text)

    def test_edit_rename_and_forget(self):
        st = self.state()
        arsenal.edit(st, {"op": "edit", "owner": "Lilia Valenheart", "name": "Crimson Fang", "desc": "A rising slash."})
        self.assertEqual(st["arsenal"]["Lilia Valenheart"][0]["desc"], "A rising slash.")
        arsenal.edit(st, {"op": "add", "owner": "Lilia Valenheart", "name": "Scarlet Step", "desc": "A burst of speed."})
        self.assertEqual(st["arsenal"]["Lilia Valenheart"][1]["uses"], 1)
        arsenal.edit(st, {"op": "delete", "owner": "Professor Yanagi", "name": "Lotus Ward"})
        self.assertNotIn("Professor Yanagi", st["arsenal"])
        with self.assertRaises(ValueError):
            arsenal.edit(st, {"op": "edit", "owner": "Lilia Valenheart", "name": "Nope", "desc": "x"})

    def test_the_arsenal_survives_state_edits(self):
        st = self.state()
        kept = normalize_state({**st, "arsenal": {**st["arsenal"], "Bad": "x", "": [{"name": "y"}]}})
        self.assertEqual(set(kept["arsenal"]), {"Aster", "Lilia Valenheart", "Professor Yanagi"})


if __name__ == "__main__":
    unittest.main()


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_spar_fills_both_arsenals_and_undo_forgets_them(self):
        from tests.test_core import FakeLLM, collect, make_services, new_game
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, kind="roleplay")
        s.conversations.add_npc(cid, "Lilia Valenheart", description="Expert (Mid) knight.")
        st = s.conversations.get_state(cid)
        st["player"]["name"] = "Aster"
        s.conversations.save_state(cid, st)
        llm.reply = "Lilia laughs.\n\n[[move: Lilia | Crimson Fang]]\nA red arc of aura rises to meet you.\n\nShe lands lightly."
        await collect(s.engine.send(cid, SPEECH))
        book = s.conversations.get_state(cid)["arsenal"]
        self.assertEqual([m["name"] for m in book["Aster"]], ["Chou no Mai - Manabiki"])
        self.assertEqual(book["Lilia Valenheart"][0]["tier"], "Expert (Mid)")
        last = s.conversations.list_messages(cid)[-1]
        self.assertIn("『Crimson Fang』", last["content"])
        self.assertEqual(last["meta"]["moves"][0]["name"], "Crimson Fang")
        sent = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertIn("[[move: Character | Technique name]]", sent)
        llm.reply = "Lilia steadies her breath."
        await collect(s.engine.send(cid, "I lower my sword."))
        sent = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertIn("『Crimson Fang』", sent)  # the known moves go back to the Aedo
        s.engine.undo(cid)
        s.engine.undo(cid)
        self.assertEqual(s.conversations.get_state(cid).get("arsenal") or {}, {})

    async def test_adventure_cards_keep_no_arsenal(self):
        from tests.test_core import FakeLLM, collect, make_services, new_game
        s = make_services(FakeLLM())
        cid = new_game(s, kind="adventure")
        await collect(s.engine.send(cid, SPEECH))
        self.assertNotIn("arsenal", s.conversations.get_state(cid))
