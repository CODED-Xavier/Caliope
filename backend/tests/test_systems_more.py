"""v2.36: the card sheet's shop (owned parts, buying with Credits), mission board, ranking ladder and step tracker."""
import unittest

from app import systems as sy
from tests.test_core import FakeLLM, collect, make_services, new_game
from tests.test_systems import black_sheep


def full() -> dict:
    raw = black_sheep()
    raw["shop"] = {"currency": "Credits", "prices": {"Cheap": 50, "Moderate": 150, "Expensive": 400, "Rare": 1000}}
    raw["board"] = {"size": 3, "pay_stat": "Credits", "level_stat": "Pilot Level",
                    "grades": [{"grade": "I", "pay": 100, "min_level": 1, "text": "Fortress-City chores"},
                               {"grade": "II", "pay": 250, "min_level": 3, "text": "Settlement work"},
                               {"grade": "IV", "pay": 1500, "min_level": 7, "text": "Academy contracts"}]}
    raw["ranking"] = {"size": 8, "names": ["Margaux", "Friedrich", "Tomoe", "Takeru", "Amira", "Brunhilde", "Mia", "Yusuf"],
                      "protect_days": 3}
    raw["steps"] = {"name": "Romance", "labels": ["Interest", "Testing", "Trust", "Feelings", "Reward"],
                    "people": ["Tomoe", "Amira", "Lise"], "per_day": 1}
    return sy.normalize(raw)


class ShopTests(unittest.TestCase):
    def test_owned_parts_and_buying(self):
        sys = full()
        st = sy.start_state(sys)
        self.assertIn("Hand's mace", st["owned"])
        self.assertIn("Not owned", sy.set_part(sys, st, "Thrusters", "Overhauled thrusters"))
        self.assertIn("Credits", sy.buy(sys, st, "Overhauled thrusters"))  # 0 credits
        st["values"]["Credits"] = 120
        self.assertEqual(sy.buy(sys, st, "Overhauled thrusters"), "")  # Cheap = 50
        self.assertEqual(st["values"]["Credits"], 70)
        self.assertEqual(sy.set_part(sys, st, "Thrusters", "Overhauled thrusters"), "")
        st["values"]["Credits"] = 5000
        self.assertIn("Level 4", sy.buy(sys, st, "Hydraulic brawler arm"))
        self.assertIn("duel wagers", sy.buy(sys, st, "Long rifle (two-handed)"))  # earned, not sold
        self.assertEqual(sy.price_of(sys, sy._item(sys, "Reactive skirts")), 50)

    def test_tracker_buys_and_gains(self):
        sys = full()
        st = sy.start_state(sys)
        st["values"]["Credits"] = 200
        lines = sy.apply_changes(sys, st, [{"buy": "Reactive skirts"}, {"gain": "Long rifle (two-handed)"}, {"buy": "Nope"}])
        self.assertIn("Long rifle (two-handed)", st["owned"])
        self.assertIn("Reactive skirts", st["owned"])
        self.assertEqual(st["values"]["Credits"], 150)
        self.assertEqual(len(lines), 2)


class BoardTests(unittest.TestCase):
    def test_jobs_accept_done_fail(self):
        sys = full()
        st = sy.start_state(sys)
        jobs = sy.board_post(sys, st, [{"title": "Clear the mine", "grade": "I", "extra": "salvage"},
                                       {"title": "Escort", "grade": "II", "extra": "a contact"},
                                       {"title": "Deep recovery", "grade": "IV", "extra": "a core"},
                                       {"title": "Too many", "grade": "I"}], day=1)
        self.assertEqual(len(jobs), 3)
        self.assertEqual(jobs[0]["pay"], 100)
        self.assertIn("Level 3", sy.board_act(sys, st, jobs[1]["id"], "accept", day=1))
        self.assertEqual(sy.board_act(sys, st, jobs[0]["id"], "accept", day=1), "")
        self.assertEqual(sy.board_act(sys, st, jobs[0]["id"], "done", day=2), "")
        self.assertEqual(st["values"]["Credits"], 100)
        self.assertIn("Clear the mine", st["board"]["log"][0])
        self.assertFalse(sy.board_stale(sys, st, day=3))
        self.assertTrue(sy.board_stale(sys, st, day=8))  # a new week: new jobs

    def test_prompt_shows_active(self):
        sys = full()
        st = sy.start_state(sys)
        jobs = sy.board_post(sys, st, [{"title": "Clear the mine", "grade": "I"}], day=1)
        sy.board_act(sys, st, jobs[0]["id"], "accept", day=1)
        self.assertIn("Clear the mine", sy.prompt_text(sys, st))


class RankingTests(unittest.TestCase):
    def test_duels(self):
        sys = full()
        st = sy.start_state(sys)
        self.assertIsNone(st["ranking"]["player"])
        self.assertEqual(sy.duel(sys, st, "Yusuf", won=True, day=2), "")
        self.assertEqual(st["ranking"]["player"], 8)  # takes the 8th place, Yusuf drops out
        self.assertNotIn("Yusuf", st["ranking"]["order"])
        self.assertEqual(sy.duel(sys, st, "Mia", won=True, day=3), "")
        self.assertEqual(st["ranking"]["player"], 7)
        self.assertEqual(st["ranking"]["order"][7], "Mia")
        self.assertIn("protected until day 6", sy.duel(sys, st, "Mia", won=True, day=4))
        self.assertEqual(sy.duel(sys, st, "Amira", won=False, day=5), "")
        self.assertEqual(st["ranking"]["player"], 7)
        sy.duel(sys, st, "Tomoe", won=False, day=6)
        self.assertEqual([d["opponent"] for d in st["ranking"]["duels"]], ["Tomoe", "Amira", "Mia"])  # the last 3, newest first
        self.assertIn("7. Valentin", sy.prompt_text(sys, st, player_name="Valentin"))


    def test_step_only_ladder(self):
        raw = full()
        raw["ranking"]["step_only"] = True
        sys = sy.normalize(raw)
        st = sy.start_state(sys)
        self.assertIn("Yusuf", sy.duel(sys, st, "Margaux", won=True, day=2))
        self.assertEqual(sy.duel(sys, st, "Yusuf", won=True, day=2), "")
        self.assertIn("Mia", sy.duel(sys, st, "Amira", won=True, day=3))


class StepTests(unittest.TestCase):
    def test_one_step_a_day(self):
        sys = full()
        st = sy.start_state(sys)
        self.assertEqual(sy.step(sys, st, "Tomoe", 1, day=1), "")
        self.assertIn("today", sy.step(sys, st, "Tomoe", 1, day=1))
        self.assertEqual(sy.step(sys, st, "Tomoe", 1, day=2), "")
        self.assertEqual(st["steps"]["Tomoe"], 2)
        self.assertIn("not on", sy.step(sys, st, "Margaux", 1, day=2))
        self.assertIn("Tomoe 2 (Testing)", sy.prompt_text(sys, st))


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def test_tracker_and_endpoints_state(self):
        llm = FakeLLM()
        s = make_services(llm)
        base = s.conversations.get(new_game(s, systems=full()))
        cid = s.conversations.create(s.scenarios.get(base["scenario_id"]))["id"]
        st = s.conversations.get_state(cid)
        self.assertIn("owned", st["systems"])
        llm.analysis = {"system_changes": [{"stat": "Credits", "delta": 300}, {"buy": "Overhauled thrusters"},
                                           {"step": "Lise", "delta": 1}]}
        await collect(s.engine.send(cid, "I go shopping, then talk to Lise."))
        st = s.conversations.get_state(cid)["systems"]
        self.assertEqual(st["values"]["Credits"], 250)
        self.assertIn("Overhauled thrusters", st["owned"])
        self.assertEqual(st["steps"]["Lise"], 1)


if __name__ == "__main__":
    unittest.main()
