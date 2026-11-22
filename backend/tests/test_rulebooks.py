"""Tests for v0.10.0: rulebook import and rules in play."""
import io
import unittest

def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


from app.rulebooks import RulebookError, ocr_available, read_pdf, read_text, split_sections
from tests.test_core import FakeLLM, collect, make_services, new_game

GRAPPLE = ("When you want to grab a creature or wrestle with it, you can use the Attack action to make a special melee attack, "
           "a grapple. The target must be no more than one size larger than you. Using at least one free hand, you try to seize "
           "the target by making a grapple check instead of an attack roll: a Strength (Athletics) check contested by the target's "
           "Strength (Athletics) or Dexterity (Acrobatics) check. If you succeed, you subject the target to the grappled condition. ")
FALLING = ("A fall from a great height is one of the most common hazards facing an adventurer. At the end of a fall, a creature "
           "takes 1d6 bludgeoning damage for every 10 feet it fell, to a maximum of 20d6. The creature lands prone, unless it "
           "avoids taking damage from the fall. ")
RESTING = ("A short rest is a period of downtime, at least 1 hour long, during which a character does nothing more strenuous than "
           "eating, drinking, reading, and tending to wounds. A long rest is a period of extended downtime, at least 8 hours long. ")


def make_pdf(pages: list[list[tuple[str, str]]], as_images: bool = False) -> bytes:
    """A small PDF. Each page is a list of (heading, body). as_images=True makes a 'scanned' book (no text layer)."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from PIL import Image, ImageDraw, ImageFont
    import textwrap

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for page in pages:
        if as_images:
            img = Image.new("L", (1275, 1650), 255)
            d = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", 28)
            except OSError:
                font = ImageFont.load_default()
            y = 80
            for heading, body in page:
                d.text((80, y), heading, fill=0, font=font); y += 60
                for line in textwrap.wrap(body, 70):
                    d.text((80, y), line, fill=0, font=font); y += 40
                y += 30
            c.drawImage(ImageReader(img), 0, 0, width=letter[0], height=letter[1])
        else:
            y = 740
            for heading, body in page:
                c.setFont("Helvetica-Bold", 14); c.drawString(60, y, heading); y -= 22
                c.setFont("Helvetica", 10)
                for line in textwrap.wrap(body, 95):
                    c.drawString(60, y, line); y -= 14
                y -= 16
        c.showPage()
    c.save()
    return buf.getvalue()


BOOK = [[("Grappling", GRAPPLE * 2)], [("Falling", FALLING * 2), ("Resting", RESTING * 2)]]


@unittest.skipUnless(_has("reportlab"), "making test PDFs needs reportlab")
class ReadingTests(unittest.TestCase):
    def test_text_pdf_sections_and_pages(self):
        pages, info = read_pdf(make_pdf(BOOK), use_ocr=False)
        self.assertEqual(info["pages"], 2)
        sections = split_sections(pages)
        heads = {s["heading"]: s["page"] for s in sections}
        self.assertEqual(heads.get("Grappling"), 1)
        self.assertEqual(heads.get("Falling"), 2)
        self.assertIn("Resting", heads)
        self.assertTrue(all(len(s["text"].split()) <= 260 for s in sections))

    @unittest.skipUnless(ocr_available(), "Tesseract is not installed here")
    def test_scanned_pdf_uses_ocr(self):
        pages, info = read_pdf(make_pdf([[("Falling", FALLING * 2)]], as_images=True))
        self.assertEqual(info["ocr_pages"], 1)
        self.assertIn("bludgeoning", pages[0].lower())

    def test_text_file_and_markdown_headings(self):
        pages = read_text(("# Grappling\n" + GRAPPLE + "\n\n# Falling\n" + FALLING * 2).encode())
        heads = [s["heading"] for s in split_sections(pages)]
        self.assertEqual(heads[:2], ["Grappling", "Falling"])

    def test_bad_pdf(self):
        with self.assertRaises(RulebookError):
            read_pdf(b"%PDF-1.4 broken", use_ocr=False)


@unittest.skipUnless(_has("reportlab"), "making test PDFs needs reportlab")
class RulebookFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.llm = FakeLLM()
        self.s = make_services(self.llm)
        rb = self.s.rulebooks
        self.book = rb.create("Basic Rules", "dnd5e", "basic.pdf")
        rb.import_bytes(self.book["id"], make_pdf(BOOK), "basic.pdf")

    async def test_import_status_and_search(self):
        book = self.s.rulebooks.get(self.book["id"])
        self.assertEqual(book["status"], "ready")
        self.assertGreaterEqual(book["sections"], 3)
        found = await self.s.rulebooks.search([book["id"]], "how does grappling work", k=2)
        self.assertEqual(found[0]["heading"], "Grappling")

    async def test_empty_or_scanned_without_ocr_reports_error(self):
        rb = self.s.rulebooks
        b = rb.create("Blank")
        rb.import_bytes(b["id"], b"   ", "blank.txt")
        self.assertEqual(rb.get(b["id"])["status"], "error")

    async def test_rules_and_house_rules_reach_the_gm(self):
        rb = self.s.rulebooks
        rb.update(self.book["id"], house_rules="Falling damage is 1d10 per 10 feet in this campaign.")
        cid = new_game(self.s, "gm_world", rulebooks=[self.book["id"]])
        await collect(self.s.engine.send(cid, "I jump down from the 30 feet cliff, what fall damage do I take?"))
        prompt = self.llm.stream_calls[-1]
        self.assertIn("## House rules (they win over the rulebook)", prompt[0]["content"])
        self.assertIn("1d10 per 10 feet", prompt[0]["content"])
        self.assertIn("## Rules reference", prompt[-1]["content"])
        self.assertIn("bludgeoning", prompt[-1]["content"])
        # small talk does not pull rules in
        await collect(self.s.engine.send(cid, "\"Hello there, friend.\""))
        self.assertNotIn("## Rules reference", self.llm.stream_calls[-1][-1]["content"])

    async def test_cards_without_books_are_unchanged(self):
        cid = new_game(self.s, "gm_world")
        await collect(self.s.engine.send(cid, "How does grappling work?"))
        self.assertNotIn("Rules reference", self.llm.stream_calls[-1][-1]["content"])

    async def test_delete(self):
        self.s.rulebooks.delete(self.book["id"])
        self.assertEqual(self.s.rulebooks.list(), [])


if __name__ == "__main__":
    unittest.main()
