"""Tests for the world calendar and clock."""
import unittest

from app import worldtime as wt
from tests.test_core import FakeLLM, collect, make_services, new_game

FANTASY = wt.normalize_calendar({"enabled": True, "preset": "fantasy",
                                 "start": {"year": 812, "month": 11, "day": 3, "hour": 19, "minute": 40, "weekday": 4}})


class CalendarTests(unittest.TestCase):
    def test_normalize_and_format(self):
        c = FANTASY
        self.assertEqual(len(c["months"]), 12)
        self.assertEqual(wt.format_now(c, 0), "Starday, 3 Frostmoon, 812 AE · 19:40 (evening)")
        # 5 hours later it is the next day
        d = wt.now(c, 5 * 60)
        self.assertEqual((d["day"], d["weekday"], d["hour"], d["minute"]), (4, 5, 0, 40))
        # a year rolls over
        d = wt.now(c, (30 + 30 - 2) * 1440)
        self.assertEqual((d["year"], d["month"], d["day"]), (813, 1, 1))
        broken = wt.normalize_calendar({"months": [{"name": "Only", "days": 0}], "weekdays": [], "start": {"month": 9, "day": 99, "hour": 99}})
        self.assertEqual(broken["months"], [{"name": "Only", "days": 1}])
        self.assertEqual(broken["start"]["month"], 1)
        self.assertEqual(broken["start"]["hour"], 23)
        self.assertEqual(len(broken["weekdays"]), 7)
        for odd in (5, True, 2.5, "Moon"):  # a hand-edited card with a number where a list goes
            got = wt.normalize_calendar({"months": odd, "weekdays": odd})
            self.assertEqual(len(got["weekdays"]), 7)
            self.assertEqual(len(got["months"]), 12)

    def test_week_ahead_counts_days(self):
        text = wt.week_ahead(FANTASY, 0)
        self.assertTrue(text.startswith("Tomorrow: Stoneday 4 Frostmoon. In 2 days: Sunday 5 Frostmoon"))

    def test_parse_when(self):
        c = FANTASY  # today is Starday (index 4)
        self.assertEqual(wt.parse_when(c, "tomorrow", 0), 1)
        self.assertEqual(wt.parse_when(c, "on Sunday", 0), 2)
        self.assertEqual(wt.parse_when(c, "next Starday", 0), 7)
        self.assertEqual(wt.parse_when(c, "in three days", 0), 3)
        self.assertEqual(wt.parse_when(c, "em 2 semanas", 0), 14)
        self.assertEqual(wt.parse_when(c, "the 10th of Frostmoon", 0), 7)
        self.assertEqual(wt.parse_when(c, "1 Deepwinter", 0), 58)
        self.assertIsNone(wt.parse_when(c, "someday", 0))

    def test_minutes_until(self):
        c = FANTASY  # 19:40
        self.assertEqual(wt.minutes_until(c, 0, "2 days"), 2 * 1440)
        self.assertEqual(wt.minutes_until(c, 0, "for three hours"), 180)
        self.assertEqual(wt.minutes_until(c, 0, "until morning"), 4 * 60 + 8 * 60 + 20)  # next 08:00
        self.assertEqual(wt.minutes_until(c, 0, "until Sunday"), 2 * 1440 - (19 * 60 + 40) + 8 * 60)  # Sunday 08:00
        self.assertEqual(wt.minutes_until(c, 0, "until tomorrow evening"), 1440 - (19 * 60 + 40) + 18 * 60)
        self.assertIsNone(wt.minutes_until(c, 0, "until I feel better"))

    def test_parse_skip(self):
        c = FANTASY
        self.assertEqual(wt.parse_skip(c, "/wait 2 days", 0)[0], 2880)
        with self.assertRaises(ValueError):
            wt.parse_skip(c, "/wait forever", 0)
        self.assertEqual(wt.parse_skip(c, "*I lie down and sleep until morning.*", 0)[0], 12 * 60 + 20)
        self.assertEqual(wt.parse_skip(c, "We travel for three days toward the capital.", 0)[0], 3 * 1440)
        self.assertIsNone(wt.parse_skip(c, '"I will wait until Sunday for you," I say.', 0))  # speech never skips
        self.assertIsNone(wt.parse_skip(c, "I wait for her answer.", 0))
        self.assertIsNone(wt.parse_skip(c, "Until Sunday then.", 0))  # no waiting verb

    def test_events(self):
        c = FANTASY
        st = {"clock": {"minutes": 0}, "events": []}
        ev = wt.add_event(st, c, "Harvest festival in the square", "Sunday at noon")
        self.assertEqual((ev["day"], ev["hour"]), (2, 12))
        self.assertIsNone(wt.add_event(st, c, "Harvest festival in the square", "Sunday"))  # no duplicates
        self.assertIsNone(wt.add_event(st, c, "the harvest festival", "next Starday"))  # a repeat in other words
        self.assertIsNotNone(wt.add_event(st, c, "Duel", "", days_guess=5))  # the model's count when words fail
        self.assertIsNone(wt.add_event(st, c, "Someday", "one day"))
        self.assertIn("In 2 days (Sunday 5 Frostmoon at 12:00): Harvest festival", wt.gm_notes(st, c))
        self.assertEqual([e["text"] for e in wt.events_between(st, c, 0, 3 * 1440)], ["Harvest festival in the square"])


class WeatherTests(unittest.TestCase):
    def test_seasons_and_persistence(self):
        c = FANTASY
        self.assertEqual(wt.season_of(c, 1), "winter")
        self.assertEqual(wt.season_of(c, 7), "summer")
        self.assertEqual(wt.weather_on(c, 10, 5), wt.weather_on(c, 10, 5))  # same day, same seed: same weather
        winter = {wt.weather_on(c, d, 1) for d in range(0, 50)}
        self.assertTrue(winter <= {w for w, _ in wt.WEATHER["winter"]} | {w for w, _ in wt.WEATHER["autumn"]})
        dry = dict(c, climate="dry")
        self.assertFalse(any("rain" in wt.weather_on(dry, d, 3) for d in range(200)))
        st = {"clock": {"minutes": 0, "seed": 9}}
        wt.advance(st, c, 1440)
        self.assertEqual(st["weather"], wt.weather_on(c, wt.day_index(c, 1440), 9))
        self.assertIsNone(wt.advance({"clock": {"minutes": 0}}, dict(c, climate="none"), 10).get("weather"))


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.llm = FakeLLM()
        self.s = make_services(self.llm)
        self.cid = new_game(self.s, calendar={"enabled": True, "preset": "fantasy",
                                              "start": {"year": 812, "month": 11, "day": 3, "hour": 19, "minute": 40, "weekday": 4}})

    async def test_start_skip_tracker_and_undo(self):
        st = self.s.conversations.get_state(self.cid)
        self.assertEqual(st["clock"]["minutes"], 0)
        self.assertTrue(st["weather"])  # rolled by the app from the season
        self.assertIn("Starday, 3 Frostmoon", st["date_label"])

        self.llm.analysis = {"minutes_passed": 2000, "appointments": [{"text": "Mira's festival", "when": "Sunday", "days_from_now": 9}],
                             "time": "noon"}
        await collect(self.s.engine.send(self.cid, "I ask Mira about the festival."))
        st = self.s.conversations.get_state(self.cid)
        self.assertEqual(st["clock"]["minutes"], 12 * 60)  # capped: the story never jumps more than 12 hours by itself
        self.assertEqual(st["events"][0]["day"], 2)  # Sunday 5 Frostmoon (counted by the app, not the model's 9)
        self.assertIn("Date and time (kept by the app)", self.llm.stream_calls[-1][-1]["content"])
        tracker_prompt = self.llm.chat_calls[-1][0][0]["content"]
        self.assertIn("minutes_passed", tracker_prompt)
        self.assertIn("minutes_passed", self.llm.chat_calls[-1][1]["required"])
        self.assertNotIn("time", self.llm.chat_calls[-1][1]["required"])

        self.llm.analysis = {}
        events = await collect(self.s.engine.send(self.cid, "/wait until Sunday"))
        user = next(e["message"] for e in events if e["type"] == "user_message")
        self.assertTrue(user["content"].startswith("⏳ Time passes"))
        self.assertIn("Mira's festival", user["content"])
        st = self.s.conversations.get_state(self.cid)
        self.assertTrue(st["date_label"].startswith("Sunday, 5 Frostmoon"))
        self.s.engine.undo(self.cid)  # undo removes the skip turn (and its reply): the clock goes back
        self.assertEqual(self.s.conversations.get_state(self.cid)["clock"]["minutes"], 12 * 60)

    async def test_wait_without_calendar(self):
        cid = new_game(self.s)
        events = await collect(self.s.engine.send(cid, "/wait 2 days"))
        self.assertEqual(events[0]["type"], "error")
        self.assertIn("no calendar", events[0]["message"])


class RainyTests(unittest.TestCase):
    def test_rainy_climate_rains_more(self):
        wet = ("rain", "drizzle", "storm", "fog", "snow", "overcast")
        def share(climate):
            cal = wt.normalize_calendar({"climate": climate})
            days = [wt.weather_on(cal, d, 7) for d in range(0, 730)]
            return sum(any(x in w for x in wet) for w in days) / len(days)
        self.assertEqual(wt.normalize_calendar({"climate": "rainy"})["climate"], "rainy")
        self.assertGreater(share("rainy"), share("temperate") + 0.15)


if __name__ == "__main__":
    unittest.main()
