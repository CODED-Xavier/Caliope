"""Narrated fights counted by the app: exchanges, EXP by difficulty, streak, bonus and grade-ups (Compendium part 2)."""
import unittest

from app import fights


def sheet(**extra):
    return {"card_status": {"Body": "D+ [20/100]", "Mana": "D [0/100]", "INT": "C- [90/100]", "Divinity": "D- [0/100]",
                            "Martial": "7", "Magic": "3", "Knowledge": "6", "Soul": "6", **extra}}


CFG = fights.normalize(fights.LUMENCIA)


class TagTests(unittest.TestCase):
    def test_tags_are_taken_out(self):
        text, starts, ends = fights.take_tags("Lilia raises her blade.\n[[fight: Lilia Valenheart | spar]]\nShe lunges.")
        self.assertEqual(starts, [("Lilia Valenheart", "spar")])
        self.assertNotIn("[[", text)
        text, starts, ends = fights.take_tags("She yields.\n[[fight end: won | Body, INT]]")
        self.assertEqual(ends, [("won", ["Body", "INT"])])
        self.assertEqual(text, "She yields.")

    def test_kinds_and_results_in_portuguese(self):
        _, starts, _ = fights.take_tags("[[luta: Aria | duelo]]")
        self.assertEqual(starts, [("Aria", "spar")])
        _, _, ends = fights.take_tags("[[fight end: derrota | Mana]]")
        self.assertEqual(ends[0][0], "lost")
        self.assertEqual(fights.kind_of("lethal trial"), "lethal")
        self.assertEqual(fights.kind_of("training drill"), "drill")

    def test_bad_config_is_empty(self):
        self.assertEqual(fights.normalize({"kinds": {}}), {})
        self.assertEqual(fights.normalize("x"), {})


class ExpTests(unittest.TestCase):
    def test_a_short_spar_gets_the_low_end_and_the_bonus(self):
        st = sheet()
        fights.start(st, "Lilia", "spar")
        lines = fights.finish(CFG, st, "won", ["Body"], day=0)
        self.assertEqual(st["card_status"]["Body"], "D+ [35/100]")  # 10 + 5 (Martial 7)
        self.assertIn("Body +15 EXP", lines[1])
        self.assertEqual(st["card_status"]["Battles Today"], "1 (1x)")
        self.assertEqual(st["card_status"]["Total"], "1")
        self.assertFalse(st["fight"]["active"])

    def test_a_long_spar_counts_as_a_battle_and_the_second_stat_gets_half(self):
        st = sheet()
        fights.start(st, "Elara", "spar")
        for _ in range(5):
            fights.count_turn(st, "I strike low and parry her counter.")
        self.assertEqual(st["fight"]["exchanges"], 6)
        lines = fights.finish(CFG, st, "won", ["Body", "INT"], day=0)
        self.assertIn("Battle", lines[0])
        self.assertEqual(st["card_status"]["Body"], "D+ [60/100]")  # 35 + 5
        self.assertEqual(st["card_status"]["INT"], "C [8/100]")  # 90 + 18 rolls over: grade up
        self.assertIn("grade up: C- → C", lines[2])

    def test_the_streak_and_a_loss(self):
        st = sheet()
        for result, today in (("won", 1), ("won", 2), ("lost", 3)):
            fights.start(st, "X", "spar")
            fights.finish(CFG, st, result, ["Mana"], day=3)
            self.assertEqual(st["fight_log"]["today"], today)
        # 10 (1x) + round(10*1.25)=12 + round(10*1.5*0.75)=11
        self.assertEqual(st["card_status"]["Mana"], "D [33/100]")
        fights.start(st, "X", "spar")
        fights.finish(CFG, st, "won", ["Mana"], day=4)  # a new day: the streak starts again
        self.assertEqual(st["fight_log"]["today"], 1)
        self.assertEqual(st["card_status"]["Total"], "4")

    def test_unknown_stats_fall_to_the_first_and_missing_bars_are_skipped(self):
        st = sheet()
        fights.start(st, "X", "drill")
        fights.finish(CFG, st, "won", ["Swordplay"], day=0)
        self.assertEqual(st["card_status"]["Body"], "D+ [30/100]")  # drill 5 + bonus 5
        st = {"card_status": {}}
        fights.start(st, "X", "spar")
        self.assertEqual(len(fights.finish(CFG, st, "won", ["Body"], day=0)), 1)  # only the headline

    def test_a_quiet_fight_closes_with_no_exp(self):
        st = sheet()
        fights.start(st, "X", "battle")
        closes = [fights.count_turn(st, "We walk to the dining hall and talk.") for _ in range(fights.QUIET_LIMIT)]
        self.assertEqual(closes[-1], True)
        self.assertIn("faded out", fights.drop(st))
        self.assertEqual(st["card_status"]["Body"], "D+ [20/100]")

    def test_no_fight_no_finish(self):
        self.assertEqual(fights.finish(CFG, sheet(), "won", ["Body"], 0), [])

    def test_the_prompt(self):
        st = sheet()
        self.assertIn("[[fight:", fights.prompt_text(CFG, st))
        fights.start(st, "Lilia", "spar")
        self.assertIn("with Lilia is going on", fights.prompt_text(CFG, st))
        self.assertEqual(fights.prompt_text({}, st), "")


if __name__ == "__main__":
    unittest.main()


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_narrated_spar_pays_exp_into_the_sheet(self):
        from tests.test_core import FakeLLM, collect, make_services, new_game
        llm = FakeLLM()
        s = make_services(llm)
        book = s.rulebooks.create_ruleset("Lumencia EXP", "Fights are counted.", "fights")
        book = s.rulebooks.update(book["id"], fight_exp=fights.LUMENCIA)
        self.assertEqual(book["fight_exp"]["stats"][0], "Body")
        cid = new_game(s, kind="roleplay", rulebooks=[book["id"]])
        st = s.conversations.get_state(cid)
        st["card_status"] = sheet()["card_status"]
        s.conversations.save_state(cid, st)
        llm.reply = "Lilia draws her blade.\n[[fight: Lilia | spar]]\nShe circles you."
        await collect(s.engine.send(cid, "I challenge Lilia to a spar."))
        sent = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertIn("Fights are counted by the app", sent)
        last = s.conversations.list_messages(cid)[-1]
        self.assertNotIn("[[fight", last["content"])
        self.assertIn("begins", last["meta"]["fight_lines"][0])
        llm.reply = "Steel rings. She gives ground."
        await collect(s.engine.send(cid, "I strike low and parry her counter."))
        self.assertEqual(s.conversations.get_state(cid)["fight"]["exchanges"], 2)
        llm.reply = "She yields, laughing.\n[[fight end: won | Body]]"
        await collect(s.engine.send(cid, "I feint and slash at her guard."))
        st = s.conversations.get_state(cid)
        self.assertFalse(st["fight"]["active"])
        self.assertEqual(st["card_status"]["Body"], "D+ [37/100]")  # 10 + round(5*2/5)=2 → 12, + 5 bonus
        self.assertTrue(any("Body +17 EXP" in x for x in s.conversations.list_messages(cid)[-1]["meta"]["fight_lines"]))
        s.engine.undo(cid)  # undo takes the EXP back
        self.assertEqual(s.conversations.get_state(cid)["card_status"]["Body"], "D+ [20/100]")


class BoardGradeNameTests(unittest.TestCase):
    def test_long_grade_names_are_kept(self):
        from app.systems import normalize
        sys = normalize({"board": {"grades": [{"grade": "Outskirts", "pay": 60}, {"grade": "Expedition", "pay": 400}]},
                         "stats": [{"key": "Gold", "kind": "number"}]})
        self.assertEqual([g["grade"] for g in sys["board"]["grades"]], ["Outskirts", "Expedition"])
