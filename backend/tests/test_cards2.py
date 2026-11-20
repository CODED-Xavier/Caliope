"""Step 2: card starts (routes), the picture folder, R2 signing."""
import asyncio
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app import cardpics, r2, routes
from tests.test_core import FakeLLM, collect, make_services

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 40


def card(s, **extra):
    data = {"name": "Lumencia", "mode": "gm_cast", "kind": "roleplay", "opening_message": "The academy gates open.",
            "alternate_openings": ["A storm over the chapel."],
            "npcs": [{"name": "Artemis Valen", "met": False}, {"name": "Lilia", "met": False},
                     {"name": "Bishop Corvin", "met": False}],
            **extra}
    return s.scenarios.create(data)


class StartTests(unittest.IsolatedAsyncioTestCase):
    def test_starts_list_and_normalize(self):
        s = make_services()
        sc = card(s, starts=[{"name": "Cult member", "opening": "Black candles.", "setting": "An evil academy.",
                              "focus": ["Bishop Corvin"], "scenes": ["The greeting.", "The ceremony."]},
                             {"name": ""}])
        ids = [x["id"] for x in routes.starts_of(sc["data"])]
        self.assertEqual(ids, ["default", "alt-1", "cult-member"])
        with self.assertRaises(ValueError):
            routes.resolve(sc["data"], "nope")

    async def test_cult_route_game(self):
        llm = FakeLLM()
        s = make_services(llm)
        sc = card(s, starts=[{"name": "Cult member", "opening": "Black candles burn.", "setting": "An evil academy that trains cultists.",
                              "focus": ["Bishop Corvin"], "scenes": ["SCENE ONE: the greeting.", "SCENE TWO: the ceremony."]}])
        conv = s.conversations.create(s.scenarios.get(sc["id"]), start="cult-member")
        cid = conv["id"]
        msgs = s.conversations.list_messages(cid)
        self.assertEqual(msgs[0]["content"], "Black candles burn.")
        met = {n["name"]: n["met"] for n in s.conversations.list_npcs(cid)}
        self.assertTrue(met["Bishop Corvin"])
        self.assertFalse(met["Artemis Valen"])
        await collect(s.engine.send(cid, "I kneel."))
        prompt = llm.stream_calls[-1]
        text = "\n".join(m["content"] for m in prompt)
        self.assertIn("An evil academy that trains cultists", prompt[0]["content"])  # route in the stable part
        self.assertIn("SCENE ONE", text)
        self.assertNotIn("SCENE TWO", text)
        await collect(s.engine.send(cid, "I rise."))
        text = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertIn("SCENE TWO", text)
        await collect(s.engine.send(cid, "I wait."))
        text = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertNotIn("Planned scene", text)
        # undo puts the last scene back in line
        s.engine.undo(cid)
        s.engine.undo(cid)
        self.assertEqual(s.conversations.get_state(cid)["script"]["next"], 1)

    def test_default_and_alternate(self):
        s = make_services()
        sc = card(s)
        cid = s.conversations.create(s.scenarios.get(sc["id"]), start="alt-1")["id"]
        self.assertEqual(s.conversations.list_messages(cid)[0]["content"], "A storm over the chapel.")
        cid = s.conversations.create(s.scenarios.get(sc["id"]))["id"]
        self.assertEqual(s.conversations.list_messages(cid)[0]["content"], "The academy gates open.")


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.src = self.root / "pics"
        for who, nums in {"ártemis": [1, 2, 4], "LILIA": [1], "Stranger": [1]}.items():
            (self.src / who).mkdir(parents=True)
            for n in nums:
                (self.src / who / f"{n}.png").write_bytes(PNG)
        (self.src / "Bishop Corvin.png").write_bytes(PNG)
        (self.src / "notes.txt").write_text("x")

    def test_match_names(self):
        names = ["Artemis Valen", "Lilia", "Lilia's Mother", "Bishop Corvin"]
        self.assertEqual(cardpics.match_name("ÁRTEMIS", names), "Artemis Valen")
        self.assertEqual(cardpics.match_name("lilia", names), "Lilia")
        self.assertEqual(cardpics.match_name("corvin", names), "Bishop Corvin")
        self.assertIsNone(cardpics.match_name("Kael", names))

    def test_scan_and_apply(self):
        names = ["Artemis Valen", "Lilia", "Bishop Corvin", "Nobody"]
        found = cardpics.scan(str(self.src), names)
        by = {c["character"]: c["moods"] for c in found["characters"]}
        self.assertEqual(by, {"Artemis Valen": [1, 2, 4], "Lilia": [1], "Bishop Corvin": [1]})
        self.assertEqual([u["folder"] for u in found["unmatched"]], ["Stranger"])
        self.assertEqual(found["missing"], ["Nobody"])
        pics = cardpics.apply(found, {}, self.root / "out", "/api/cardpics/1", {"Stranger": "Nobody"})
        art = pics["Artemis Valen"]
        self.assertEqual(art["default"], "/api/cardpics/1/artemis_valen/1.png")
        moods = {m["n"]: m["url"] for m in art["moods"]}
        self.assertEqual(moods[4], "/api/cardpics/1/artemis_valen/4.png")
        self.assertEqual(moods[5], moods[4])          # Disgusted falls back to Angry
        self.assertEqual(moods[6], moods[2])          # Blushing falls back to Happy
        self.assertEqual(moods[3], moods[1])          # Sad falls back to Standard
        self.assertIn("Nobody", pics)                 # picked by hand
        self.assertTrue((self.root / "out" / "artemis_valen" / "4.png").is_file())


class R2Tests(unittest.TestCase):
    def test_presign_matches_aws_example(self):
        url = r2.presign("GET", "examplebucket.s3.amazonaws.com", "/test.txt", "AKIAIOSFODNN7EXAMPLE",
                         "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", region="us-east-1", expires=86400,
                         now=dt.datetime(2013, 5, 24, tzinfo=dt.timezone.utc))
        self.assertTrue(url.endswith("X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"))

    def test_download_link_needs_keys(self):
        with self.assertRaises(r2.R2Error):
            r2.download_link({}, "r2:cards/x/1.png")
        link = r2.download_link({"r2_account_id": "acc", "r2_bucket": "pics", "r2_access_key_id": "a",
                                 "r2_secret_access_key": "b"}, "r2:cards/lumencia/artemis/1.png")
        self.assertTrue(link.startswith("https://acc.r2.cloudflarestorage.com/pics/cards/lumencia/artemis/1.png?"))


if __name__ == "__main__":
    unittest.main()
