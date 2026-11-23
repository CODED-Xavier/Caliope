"""Characters that belong to one route (the cult's Seminary students) are left out of the card's other routes."""
import unittest

from tests.test_core import make_services


class RouteCastTests(unittest.TestCase):
    def test_route_only_characters(self):
        s = make_services()
        card = s.scenarios.create({
            "name": "Academy", "mode": "gm_cast", "opening_message": "The gates open.",
            "npcs": [{"name": "Lilia"}, {"name": "Elara", "route": "dark-route"}],
            "starts": [{"id": "dark-route", "name": "Dark route", "opening": "Bells below."}]})
        light = s.conversations.create(s.scenarios.get(card["id"]))
        dark = s.conversations.create(s.scenarios.get(card["id"]), start="dark-route")
        self.assertEqual([n["name"] for n in s.conversations.list_npcs(light["id"])], ["Lilia"])
        self.assertEqual(sorted(n["name"] for n in s.conversations.list_npcs(dark["id"])), ["Elara", "Lilia"])
        self.assertEqual(s.scenarios.get(card["id"])["data"]["npcs"][1]["route"], "dark-route")


    def test_the_default_start_can_have_scenes(self):
        from app import routes
        from app.prompts import planned_scene
        s = make_services()
        card = s.scenarios.create({
            "name": "Academy", "mode": "gm_cast", "opening_message": "The gates open.",
            "npcs": [{"name": "Lilia"}, {"name": "Elara", "route": "dark-route"}],
            "default_start": {"name": "Light route", "description": "Enrolment Day", "setting": "The academy above.",
                              "scenes": ["Registration with your department's professor.", "The ceremony."]},
            "starts": [{"id": "dark-route", "name": "Dark route", "opening": "Bells below."}]})
        data = s.scenarios.get(card["id"])["data"]
        self.assertEqual(routes.starts_of(data)[0]["name"], "Light route")
        conv = s.conversations.create(s.scenarios.get(card["id"]))
        self.assertEqual(conv["scenario"]["route"]["id"], "default")
        self.assertEqual([n["name"] for n in s.conversations.list_npcs(conv["id"])], ["Lilia"])
        state = s.conversations.get_state(conv["id"])
        self.assertIn("Registration", planned_scene(conv["scenario"]["route"], state))
        self.assertEqual(s.conversations.list_messages(conv["id"])[0]["content"], "The gates open.")
        routes.advance(state, conv["scenario"]["route"])
        self.assertIn("ceremony", planned_scene(conv["scenario"]["route"], state))

    def test_a_plain_default_start_is_no_route(self):
        from app import routes
        s = make_services()
        card = s.scenarios.create({"name": "Plain", "mode": "gm_cast", "opening_message": "Hi."})
        self.assertIsNone(routes.resolve(s.scenarios.get(card["id"])["data"], ""))
        self.assertNotIn("route", s.conversations.create(s.scenarios.get(card["id"]))["scenario"])


if __name__ == "__main__":
    unittest.main()
