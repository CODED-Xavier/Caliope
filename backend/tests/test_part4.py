"""Part 4: PC scan suggestions and ✨ Correct my text."""
import unittest

from app import hardware, writing_help
from tests.test_core import FakeLLM


class SuggestTests(unittest.TestCase):
    def pick(self, vram, ram=16):
        return hardware.suggest({"gpus": [{"name": "GPU", "vram_gb": vram}] if vram is not None else [], "ram_gb": ram})

    def test_by_card(self):
        self.assertEqual(self.pick(8.0)["search"], "Stheno-v3.2")
        self.assertEqual(self.pick(8.0)["file"], "Q4_K_M")
        self.assertEqual(self.pick(6.0)["file"], "Q3_K_M")
        self.assertEqual(self.pick(12.0)["search"], "Mag-Mell-R1")
        self.assertEqual(self.pick(24.0)["search"], "Cydonia-24B")
        self.assertEqual(self.pick(4.0)["search"], "Llama-3.2-3B-Instruct-GGUF")
        self.assertFalse(self.pick(None, 32)["gpu"])            # no card: the processor runs it, slowly
        self.assertIn("slow", self.pick(None, 32)["why"])

    def test_scan_never_fails(self):
        info = hardware.scan()
        self.assertIn("gpus", info)
        self.assertIn("ram_gb", info)


class CorrectTests(unittest.IsolatedAsyncioTestCase):
    async def test_correct_and_guard(self):
        llm = FakeLLM()

        async def chat(messages, json_schema=None, **kw):
            return 'Corrected text: "Hello there," I say. *I bow.*'
        llm.chat = chat
        self.assertEqual(await writing_help.correct(llm, '"helo ther," i say. *i bow*', "en"), '"Hello there," I say. *I bow.*')

        async def chatty(messages, json_schema=None, **kw):
            return "Sure! Here is a long story about the knight who bowed and then went on a quest for many days..." * 3
        llm.chat = chatty
        self.assertEqual(await writing_help.correct(llm, "*i bow*", "en"), "*i bow*")   # not a correction: kept


if __name__ == "__main__":
    unittest.main()
