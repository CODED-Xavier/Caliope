"""Reading any web page for the Muse's research: the links you give become a card (not only fan wikis).

Each link is fetched (public sites only), its menus, scripts and footers dropped, and its text kept with its headings.
A page whose sections look like a character's (Personality, Appearance, Abilities…) becomes a character; the first
page (or one marked `world:`) becomes the world; the rest become lorebook entries. A line can say what it is:
`character: https://…`, `lore: https://…`, `world: https://…`.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

from .wikiresearch import SECTION_KEYS, ResearchError, build_card, research_notes, split_page

MAX_LINKS = 30
MAX_BYTES = 3_000_000
DROP = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "button", "select", "iframe", "template"}
BLOCKS = {"p", "li", "div", "section", "article", "tr", "br", "blockquote", "dd", "dt", "table", "figcaption"}
SKIP_CLASS = re.compile(r"\b(nav|menu|footer|sidebar|breadcrumb|cookie|share|comment|advert|ad-|ads|related|toc|navbox|"
                        r"global-navigation|page-header__|wds-|mw-editsection|reference|citation)\b", re.I)


class _Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0          # inside a dropped element
        self.stack: list[tuple[str, bool]] = []
        self.heading = ""      # inside h1-h4: collected separately
        self.title = ""
        self.h1 = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "img", "hr", "meta", "link", "input"):
            if tag == "br" and not self.skip:
                self.out.append("\n")
            return
        a = dict(attrs)
        dropped = tag in DROP or bool(SKIP_CLASS.search(f"{a.get('class') or ''} {a.get('id') or ''} {a.get('role') or ''}"))
        self.stack.append((tag, dropped))
        if dropped:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "h1" and not self.skip:
            self.heading = "h1"  # the page's own name: kept apart, not a section
        elif tag in ("h2", "h3", "h4") and not self.skip:
            self.heading = tag
            self.out.append(f"\n\n{'=' * max(2, int(tag[1]))} ")
        elif tag in BLOCKS and not self.skip:
            self.out.append("\n")

    def handle_endtag(self, tag):
        while self.stack:
            t, dropped = self.stack.pop()
            if dropped:
                self.skip -= 1
            if t == tag:
                break
        if tag == "title":
            self.in_title = False
        if tag == "h1" and self.heading == "h1":
            self.heading = ""
        elif tag in ("h2", "h3", "h4") and self.heading == tag:
            self.out.append(f" {'=' * max(2, int(tag[1]))}\n")
            self.heading = ""
        elif tag in BLOCKS and not self.skip:
            self.out.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
            return
        if self.heading == "h1":
            self.h1 += data
            return
        if not self.skip and data.strip():
            self.out.append(re.sub(r"\s+", " ", data) if self.heading else data)


def page_text(html: str) -> tuple[str, str]:
    """(page title, text with == headings ==) from a page's HTML."""
    r = _Reader()
    try:
        r.feed(html)
    except Exception:  # noqa: BLE001 - broken HTML: keep what was read
        pass
    text = "".join(r.out)
    text = re.sub(r"\[\s*(edit|editar|\d+)\s*\]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    title = re.sub(r"\s*[|\-–—]\s*[^|\-–—]*(wiki|fandom|wikipedia)[^|\-–—]*$", "", r.title.strip(), flags=re.I).strip()
    h1 = re.sub(r"\s+", " ", r.h1).strip()
    return (h1 if h1 and len(h1) < 80 else title or "Page"), text


def parse_links(text: str) -> list[tuple[str, str]]:
    """'character: https://…' lines -> [(kind, url)]; kind is character, lore, world or '' (decide by the page)."""
    out = []
    for line in (text or "").splitlines():
        m = re.match(r"^\s*(?:(character|personagem|lore|world|mundo)\s*[:=]\s*)?(https?://\S+)\s*$", line, re.I)
        if m:
            kind = (m.group(1) or "").lower()
            kind = {"personagem": "character", "mundo": "world"}.get(kind, kind)
            out.append((kind, m.group(2)))
    if not out:
        raise ResearchError("Paste one link per line (https://…).")
    return out[:MAX_LINKS]


def looks_like_character(sections: dict) -> bool:
    return sum(1 for k in ("personality", "appearance", "abilities") if sections.get(k)) >= 1


async def research_links(fetch_html, links_text: str, work: str = "", language: str = ""):
    """Read the links and yield progress, then the draft card (the same shape as the wiki research)."""
    links = parse_links(links_text)
    world, chars, lore = None, [], []
    for i, (kind, url) in enumerate(links, 1):
        yield {"type": "progress", "step": f"Reading {url} ({i}/{len(links)})"}
        try:
            html = await fetch_html(url)
        except Exception as exc:  # noqa: BLE001 - one unreachable page doesn't stop the others
            yield {"type": "progress", "step": f"Skipped {url}: {exc}"}
            continue
        title, text = page_text(html)
        if len(text) < 120:
            yield {"type": "progress", "step": f"Skipped {url}: almost no text on the page"}
            continue
        page = {"title": title, **split_page(text)}
        if kind == "world" or (not kind and world is None and i == 1 and not looks_like_character(page)):
            world = page
        elif kind == "character" or (not kind and looks_like_character(page)):
            chars.append(page)
        else:
            lore.append(page)
    if not (world or chars or lore):
        raise ResearchError("None of the links could be read.")
    name = work.strip() or (world or {}).get("title") or (chars or lore)[0]["title"]
    card = build_card(name, world, chars, lore, language)
    card["description"] = f"A story in the world of {name} (researched from {len(links)} web pages)."
    yield {"type": "card", "card": card, "notes": research_notes(name, card)}


__all__ = ["research_links", "page_text", "parse_links", "SECTION_KEYS"]
