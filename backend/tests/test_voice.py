"""Step 7: the narration voice (Piper), with the program and downloads faked."""
import asyncio
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.voice import VoiceError, VoiceManager, speakable


def fake_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("piper/piper.exe", b"MZ")
        z.writestr("piper/espeak-ng-data/x", b"1")
    return buf.getvalue()


class VoiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.v = VoiceManager(Path(tempfile.mkdtemp()))

    async def fetch(self, url, progress):
        progress(5, 10)
        if url.endswith(".zip"):
            return fake_zip()
        if url.endswith(".json"):
            return b'{"audio": {"sample_rate": 22050}}'
        return b"\0" * 2_000_000

    async def test_install_and_speak(self):
        self.assertFalse(self.v.status()["engine"])
        st = await self.v.install("en_US-lessac-medium", fetch_bytes=self.fetch)
        self.assertTrue(st["engine"])
        self.assertTrue(next(x for x in st["voices"] if x["id"] == "en_US-lessac-medium")["installed"])
        calls = []

        def runner(cmd, data):
            calls.append((cmd, data))
            Path(cmd[cmd.index("--output_file") + 1]).write_bytes(b"RIFFwav")
            return type("R", (), {"returncode": 0, "stderr": b""})()

        text = "[[show: Artemis | Angry]]\n*The bell tolls.* \"Late again,\" she says.\n\nINFO\nHP: 10"
        out = self.v.speak(text, "en_US-lessac-medium", 1.25, runner=runner)
        self.assertEqual(out.read_bytes(), b"RIFFwav")
        spoken = calls[0][1].decode()
        self.assertNotIn("INFO", spoken)
        self.assertNotIn("show", spoken)
        self.assertIn("The bell tolls.", spoken)
        self.assertIn("0.800", calls[0][0])             # speed 1.25 -> length scale 0.8
        self.v.speak(text, "en_US-lessac-medium", 1.25, runner=runner)
        self.assertEqual(len(calls), 1)                   # the second time comes from the kept file

    async def test_errors(self):
        with self.assertRaises(VoiceError):
            self.v.speak("Hello", "en_US-lessac-medium")  # not downloaded
        with self.assertRaises(VoiceError):
            await self.v.install("nope", fetch_bytes=self.fetch)

    def test_speakable(self):
        self.assertEqual(speakable("**Bold** and _it_ ⚔️ go [link](http://x)"), "Bold and it go link")
