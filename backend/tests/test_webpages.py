"""The Muse's research from any web page: links you give become a draft card."""
import unittest

from app.webpages import page_text, parse_links, research_links
from app.wikiresearch import ResearchError

CHAR = """<html><head><title>Satoru Gojo | Jujutsu Kaisen Wiki | Fandom</title><script>var x=1</script></head><body>
<nav class="global-navigation">Home Shop Sign in</nav>
<h1>Satoru Gojo</h1><p>Satoru Gojo is a special grade sorcerer and a teacher at Tokyo Jujutsu High, widely seen as the strongest sorcerer of his time.</p>
<h2>Appearance<span class="mw-editsection">[edit]</span></h2><p>A tall man with white hair, usually wearing a blindfold over his blue eyes.</p>
<h2>Personality</h2><p>Playful, arrogant and childish, yet deeply devoted to raising the next generation of sorcerers.</p>
<footer>Copyright Fandom. Terms of use.</footer></body></html>"""
WORLD = """<html><head><title>Jujutsu Kaisen - Wikipedia</title></head><body><h1>Jujutsu Kaisen</h1>
<p>Jujutsu Kaisen is a story about sorcerers who fight curses, monsters born from the negative emotions of people.</p>
<p>Students at Tokyo Jujutsu High train to exorcise curses using cursed energy and their innate techniques.</p></body></html>"""
LORE = """<html><head><title>Cursed Energy</title></head><body><h1>Cursed Energy</h1>
<p>Cursed energy is the power that flows from negative emotions. Sorcerers refine it to fuel their cursed techniques, while curses are made of it entirely and grow stronger as fear spreads.</p></body></html>"""


class PageTests(unittest.TestCase):
    def test_menus_scripts_and_footers_are_dropped(self):
        title, text = page_text(CHAR)
        self.assertEqual(title, "Satoru Gojo")
        self.assertIn("== Personality ==", text)
        for gone in ("var x", "Sign in", "Copyright", "[edit]"):
            self.assertNotIn(gone, text)

    def test_link_lines(self):
        got = parse_links("character: https://a.example/gojo\nnot a link\nhttps://b.example/world\nlore=https://c.example/x")
        self.assertEqual(got, [("character", "https://a.example/gojo"), ("", "https://b.example/world"), ("lore", "https://c.example/x")])
        with self.assertRaises(ResearchError):
            parse_links("just words")


class ResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_pages_become_a_card(self):
        pages = {"https://w.example/jjk": WORLD, "https://w.example/gojo": CHAR, "https://w.example/ce": LORE}

        async def fetch(url):
            if url not in pages:
                raise OSError("unreachable")
            return pages[url]
        events = [e async for e in research_links(fetch, "\n".join([*pages, "https://w.example/missing"]), "", "pt-BR")]
        card = events[-1]["card"]
        self.assertEqual(card["name"], "Jujutsu Kaisen")
        self.assertIn("sorcerers who fight curses", card["world"])
        self.assertEqual([n["name"] for n in card["npcs"]], ["Satoru Gojo"])
        self.assertIn("Playful", card["npcs"][0]["personality"])
        names = [e["name"] for e in card["lorebook"]["entries"]]
        self.assertIn("Cursed Energy", names)
        self.assertTrue(any("Skipped https://w.example/missing" in e.get("step", "") for e in events))
        self.assertEqual(card["language"], "pt-BR")


if __name__ == "__main__":
    unittest.main()
