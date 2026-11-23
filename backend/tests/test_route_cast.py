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


if __name__ == "__main__":
    unittest.main()
