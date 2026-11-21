"""v2.0 Calíope: PixAI scene pictures and the picture service setting."""
import asyncio
import unittest

from app import scenes
from app.scenes import PixAIError, is_pixai, parse_pixai_url, pixai_paint, pixai_url
from tests.test_core import make_services


class Resp:
    def __init__(self, data, code=200):
        self.data, self.status_code, self.text = data, code, str(data)

    def json(self):
        return self.data


class FakePixAI:
    def __init__(self, polls=2, media="m123", batch=None, fail=False):
        self.polls, self.media, self.fail = polls, media, fail
        self.batch = batch or {"m123": {"urls": [{"type": "THUMBNAIL", "url": "https://cdn/t.png"},
                                                  {"type": "PUBLIC", "url": "https://cdn/full.png"}]}}
        self.calls = []

    async def post(self, url, json=None, headers=None):
        self.calls.append(("post", url, json, headers))
        return Resp({"id": "t1", "status": "waiting", "outputs": {}})

    async def get(self, url, params=None, headers=None):
        self.calls.append(("get", url, params))
        if "/v2/task/" in url:
            self.polls -= 1
            if self.fail:
                return Resp({"id": "t1", "status": "failed", "outputs": {}})
            done = self.polls <= 0
            return Resp({"id": "t1", "status": "completed" if done else "running",
                         "outputs": {"mediaUrls": [self.media]} if done else {}})
        return Resp(self.batch)


class PixAITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._poll = scenes.PIXAI_POLL_SECONDS
        scenes.PIXAI_POLL_SECONDS = 0

    def tearDown(self):
        scenes.PIXAI_POLL_SECONDS = self._poll

    def test_url_round_trip(self):
        url = pixai_url("a misty castle, dawn: cold light", 42)
        self.assertTrue(is_pixai(url))
        self.assertEqual(parse_pixai_url(url), (42, "a misty castle, dawn: cold light"))

    async def test_paint_waits_and_picks_public_link(self):
        fake = FakePixAI()
        link = await pixai_paint(pixai_url("a castle", 7), "key", "123", client=fake)
        self.assertEqual(link, "https://cdn/full.png")
        post = fake.calls[0]
        self.assertEqual(post[2]["prompt"], "a castle")
        self.assertEqual(post[2]["modelVersionId"], "123")
        self.assertEqual(post[2]["seed"], 7)
        self.assertEqual(post[3]["Authorization"], "Bearer key")

    async def test_direct_link_and_errors(self):
        self.assertEqual(await pixai_paint(pixai_url("x", 1), "k", "m", client=FakePixAI(media="https://cdn/a.png")),
                         "https://cdn/a.png")
        with self.assertRaises(PixAIError):
            await pixai_paint(pixai_url("x", 1), "", "m", client=FakePixAI())
        with self.assertRaises(PixAIError):
            await pixai_paint(pixai_url("x", 1), "k", "", client=FakePixAI())
        with self.assertRaises(PixAIError):
            await pixai_paint(pixai_url("x", 1), "k", "m", client=FakePixAI(fail=True))


class SettingTests(unittest.TestCase):
    def test_picture_service(self):
        s = make_services()
        self.assertEqual(s.settings.get("picture_service"), "pollinations")
        s.settings.update({"picture_service": "pixai", "pixai_api_key": "abc"})
        self.assertEqual(s.settings.get("picture_service"), "pixai")
        with self.assertRaises(ValueError):
            s.settings.update({"picture_service": "midjourney"})

    def test_interface_language(self):
        s = make_services()
        self.assertEqual(s.settings.get("ui_language"), "en")
        s.settings.update({"ui_language": "pt-BR"})
        self.assertEqual(s.settings.get("ui_language"), "pt-BR")
        with self.assertRaises(ValueError):
            s.settings.update({"ui_language": "fr"})


if __name__ == "__main__":
    unittest.main()
