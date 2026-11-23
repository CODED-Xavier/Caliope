"""Tests for the Jukebox."""
import tempfile
import unittest
from pathlib import Path

from app.jukebox import MusicError, clean_tags, guess_mood, sniff_audio
from tests.test_core import FakeLLM, collect, make_services, new_game

MP3 = b"ID3\x03\x00\x00\x00" + b"\x00" * 64
OGG = b"OggS" + b"\x00" * 64


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.s = make_services(FakeLLM())
        self.s.music.dir = Path(tempfile.mkdtemp())

    def test_sniff(self):
        self.assertEqual(sniff_audio(MP3), ".mp3")
        self.assertEqual(sniff_audio(OGG), ".ogg")
        self.assertEqual(sniff_audio(b"RIFF\x00\x00\x00\x00WAVEfmt "), ".wav")
        self.assertIsNone(sniff_audio(b"<html>"))

    def test_add_file_link_update_delete(self):
        m = self.s.music
        t = m.add_file(MP3, "Tavern Jig", ["tavern", "calm", "nonsense"])
        self.assertEqual(t["tags"], ["tavern", "calm"])
        self.assertTrue(t["url"].startswith("/api/music/files/") and t["url"].endswith(".mp3"))
        self.assertIsNotNone(m.file_path(t["url"].rsplit("/", 1)[1]))
        self.assertIsNone(m.file_path("../../secret.mp3"))
        with self.assertRaises(MusicError):
            m.add_file(b"<html>", "x")
        link = m.add_link("https://example.com/battle.ogg", "Battle", ["combat"], [3, "x", 3])
        self.assertEqual((link["source"], link["cards"]), ("link", [3]))
        with self.assertRaises(MusicError):
            m.add_link("https://www.youtube.com/watch?v=abc", "x")
        with self.assertRaises(MusicError):
            m.add_link("ftp://x/y.mp3", "x")
        m.update(t["id"], name="Jig", tags=["tavern"], cards=[1])
        self.assertEqual(m.get(t["id"])["cards"], [1])
        fname = t["url"].rsplit("/", 1)[1]
        m.delete(t["id"])
        self.assertIsNone(m.file_path(fname))  # the file goes too

    def test_mood_guess(self):
        self.assertEqual(guess_mood("The innkeeper slides a mug of ale across the tavern counter."), "tavern")
        self.assertEqual(guess_mood("Nice weather."), "")
        self.assertEqual(clean_tags("combat, boss,  x"), ["combat", "boss"])


class TaggingTests(unittest.TestCase):
    def test_moods_from_song_names(self):
        from app.jukebox import suggest_tags
        self.assertEqual(suggest_tags("Final_Boss-Battle"), ["combat", "boss"])
        self.assertIn("tavern", suggest_tags("Taverna do Porto (jig)"))
        self.assertIn("night", suggest_tags("Moonlit Nocturne"))
        self.assertEqual(suggest_tags("track 07"), [])

    def test_new_moods_in_portuguese_stories(self):
        self.assertEqual(guess_mood("A professora começa a aula; os alunos abrem os cadernos na sala de aula."), "academy")
        self.assertEqual(guess_mood("Sob a lua, as estrelas brilham na noite fria."), "night")

    def test_autotag_and_bulk(self):
        import tempfile
        from pathlib import Path
        from app.db import Database
        from app.jukebox import MusicLibrary
        m = MusicLibrary(Database(":memory:"), Path(tempfile.mkdtemp()))
        a = m.add_link("https://x.example/epic_battle.mp3", "Epic Battle")
        self.assertEqual(a["tags"], ["combat", "epic"])  # tagged by its name when no mood was picked
        b = m.add_link("https://x.example/b.mp3", "Song B", tags=["calm"])
        m.update(b["id"], name="Rainy Night Piano", tags=[])
        self.assertEqual(m.get(b["id"])["suggested"], ["calm", "night"])
        self.assertEqual(m.autotag(), 1)
        self.assertEqual(m.get(b["id"])["tags"], ["calm", "night"])
        self.assertEqual(m.bulk([a["id"], b["id"], 999], add=["academy"], remove=["calm"]), 2)
        self.assertEqual(m.get(b["id"])["tags"], ["night", "academy"])


class SceneMoodTests(unittest.IsolatedAsyncioTestCase):
    async def test_tracker_sets_scene_mood(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        llm.analysis = {"scene_mood": "mystery"}
        await collect(s.engine.send(cid, "I read the letter."))
        self.assertEqual(s.conversations.get_state(cid)["scene_mood"], "mystery")
        llm.analysis = {"scene_mood": "disco"}
        await collect(s.engine.send(cid, "I wait."))
        self.assertEqual(s.conversations.get_state(cid)["scene_mood"], "mystery")  # unknown moods are ignored
        prompt = "\n".join(m["content"] for m in llm.chat_calls[-1][0])
        self.assertIn("scene_mood", prompt)


if __name__ == "__main__":
    unittest.main()
