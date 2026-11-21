"""The Muse researches an existing work (an anime, a game, a book series) on its fan wiki and drafts a card from it.

Fandom wikis (and other MediaWiki sites) have a public API. The app finds the wiki, lists its biggest character and
lore pages (the longest pages are usually the main characters and the key ideas), reads the ones you tick and turns
them into a card by code: each character's introduction, personality and appearance, the world from the work's own
page, and one lorebook entry per lore page. No model is needed, so it is quick; ✨ Fill and the Muse can polish it.
Wiki text is shared by its authors under CC BY-SA; the card is for your own games.
"""
from __future__ import annotations

import asyncio
import re
from typing import Awaitable, Callable
from urllib.parse import quote, urlparse

from .util import truncate

FetchJson = Callable[[str], Awaitable[dict]]

CHARACTER_CATEGORIES = ("Characters", "Main characters", "Main Characters", "Protagonists", "Antagonists", "Female characters",
                        "Male characters")
LORE_CATEGORIES = ("Locations", "Organizations", "Groups", "Factions", "Terminology", "Concepts", "Abilities", "Techniques",
                   "Races", "Species", "Magic", "Events", "Items", "Places")
SKIP_TITLE = re.compile(r"^(list of|gallery|.*\(disambiguation\)|.*/gallery|.*/relationships|.*/image gallery)", re.I)
SECTION_KEYS = {
    "personality": re.compile(r"^(personality|character|traits)$", re.I),
    "appearance": re.compile(r"^(appearance|physical appearance|design)$", re.I),
    "abilities": re.compile(r"^(abilities|powers|powers and abilities|abilities and powers|skills|equipment)$", re.I),
    "background": re.compile(r"^(background|history|biography|backstory|overview|summary)$", re.I),
}
MAX_PAGES = 40
GAP = 0.25  # seconds between requests: be polite with the wiki


class ResearchError(ValueError):
    pass


# ------------------------------------------------------------------ finding the wiki
def wiki_candidates(query: str) -> list[str]:
    """'Jujutsu Kaisen' -> api.php addresses to try; a pasted wiki link is used as it is."""
    q = (query or "").strip()
    if not q:
        raise ResearchError("Write the name of the work, or paste its wiki's address.")
    if q.startswith(("http://", "https://")) or "." in q.split()[0]:
        u = urlparse(q if q.startswith("http") else "https://" + q)
        if not u.hostname:
            raise ResearchError("That wiki address could not be read.")
        lang = re.match(r"^/([a-z]{2}(?:-[a-z]{2})?)/", u.path or "")
        base = f"https://{u.hostname}" + (f"/{lang.group(1)}" if lang else "")
        return [base + "/api.php"]
    words = re.sub(r"[^a-z0-9 ]+", "", q.lower().replace("&", "and")).split()
    slugs = list(dict.fromkeys(["-".join(words), "".join(words), words[0] if words else ""]))
    return [f"https://{s}.fandom.com/api.php" for s in slugs if s]


async def find_wiki(fetch: FetchJson, query: str) -> dict:
    for api in wiki_candidates(query):
        try:
            data = await fetch(api + "?action=query&meta=siteinfo&siprop=general&format=json")
        except Exception:
            continue
        general = ((data or {}).get("query") or {}).get("general") or {}
        if general.get("sitename"):
            work = ""
            if not query.strip().startswith(("http://", "https://")):
                try:  # the work's own article ("Jujutsu Kaisen" or "Jujutsu Kaisen (Manga)") gives the world
                    found = await fetch(f"{api}?action=query&list=search&srsearch={quote(query.strip())}&srlimit=1&format=json")
                    hits = ((found or {}).get("query") or {}).get("search") or []
                    work = hits[0]["title"] if hits else ""
                except Exception:
                    work = ""
            return {"api": api, "sitename": general["sitename"], "main": general.get("mainpage", ""), "work": work}
    raise ResearchError("No wiki was found for that name. Paste the wiki's address (for example https://jujutsu-kaisen.fandom.com).")


async def _category(fetch: FetchJson, api: str, cat: str, limit: int = 200) -> list[str]:
    data = await fetch(f"{api}?action=query&list=categorymembers&cmtitle={quote('Category:' + cat)}&cmtype=page&cmlimit={limit}&format=json")
    return [m["title"] for m in ((data or {}).get("query") or {}).get("categorymembers") or [] if not SKIP_TITLE.match(m.get("title", ""))]


async def _lengths(fetch: FetchJson, api: str, titles: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i in range(0, len(titles), 50):
        chunk = "|".join(titles[i:i + 50])
        data = await fetch(f"{api}?action=query&prop=info&titles={quote(chunk)}&format=json")
        for page in (((data or {}).get("query") or {}).get("pages") or {}).values():
            if page.get("title") and "missing" not in page:
                out[page["title"]] = int(page.get("length") or 0)
        await asyncio.sleep(GAP)
    return out


async def list_pages(fetch: FetchJson, api: str) -> dict:
    """The biggest character pages and lore pages of the wiki (biggest first)."""
    chars: list[str] = []
    for cat in CHARACTER_CATEGORIES:
        try:
            chars += [t for t in await _category(fetch, api, cat) if t not in chars]
        except Exception:
            continue
        if len(chars) >= 150:
            break
        await asyncio.sleep(GAP)
    lore: list[str] = []
    for cat in LORE_CATEGORIES:
        try:
            lore += [t for t in await _category(fetch, api, cat, 100) if t not in lore and t not in chars]
        except Exception:
            continue
        await asyncio.sleep(GAP)
    sizes = await _lengths(fetch, api, chars[:300] + lore[:200])
    rank = lambda titles: [{"title": t, "size": sizes.get(t, 0)} for t in sorted(titles, key=lambda t: -sizes.get(t, 0)) if t in sizes]  # noqa: E731
    return {"characters": rank(chars)[:40], "lore": rank(lore)[:30]}


# ------------------------------------------------------------------ reading pages
def _strip_templates(text: str) -> str:
    out, depth, i = [], 0, 0
    while i < len(text):
        if text.startswith("{{", i):
            depth += 1
            i += 2
        elif text.startswith("}}", i) and depth:
            depth -= 1
            i += 2
        else:
            if not depth:
                out.append(text[i])
            i += 1
    return "".join(out)


def strip_wikitext(text: str) -> str:
    t = re.sub(r"<!--.*?-->", "", text or "", flags=re.S)
    t = re.sub(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", "", t, flags=re.S | re.I)
    t = re.sub(r"\{\|.*?\|\}", "", t, flags=re.S)                       # tables
    t = _strip_templates(t)
    t = re.sub(r"\[\[(?:File|Image|Category|Archivo|Arquivo|Categoria):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", "", t, flags=re.I)
    t = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", t)
    t = re.sub(r"\[\[([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", t)
    t = re.sub(r"'{2,}", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"^[*#:;]+\s*", "- ", t, flags=re.M)
    t = re.sub(r"__[A-Z]+__", "", t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def split_page(wikitext: str) -> dict:
    """{'intro': ..., 'personality': ..., 'appearance': ..., 'abilities': ..., 'background': ...} in plain text."""
    parts = re.split(r"^(={2,4})\s*(.*?)\s*\1\s*$", wikitext or "", flags=re.M)
    out = {"intro": strip_wikitext(parts[0])}
    for i in range(1, len(parts) - 2, 3):
        title = strip_wikitext(parts[i + 1])
        body = strip_wikitext(parts[i + 2])
        for key, rx in SECTION_KEYS.items():
            if rx.match(title) and body and key not in out:
                out[key] = body
    return out


async def read_page(fetch: FetchJson, api: str, title: str) -> dict:
    data = await fetch(f"{api}?action=parse&page={quote(title)}&prop=wikitext&redirects=1&format=json")
    wikitext = (((data or {}).get("parse") or {}).get("wikitext") or {}).get("*", "")
    if not wikitext:
        raise ResearchError(f"The page '{title}' could not be read.")
    return {"title": title, **split_page(wikitext)}


def _first(text: str, limit: int) -> str:
    """The first paragraphs of a text, cut at a sentence end."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind(".\n"))
    return (cut[: end + 1] if end > limit // 2 else truncate(cut, limit)).strip()


def _name(title: str) -> str:
    return re.sub(r"\s*\((character|manga|anime|novel|game|series)\)\s*$", "", title, flags=re.I).strip()


def build_card(sitename: str, work: dict | None, characters: list[dict], lore: list[dict], language: str = "") -> dict:
    """A draft card from the pages read: the world, the characters and a lorebook."""
    title = re.sub(r"\s+(wiki|wikia)$", "", sitename, flags=re.I).strip() or "New world"
    world = _first((work or {}).get("intro") or "", 1800) or f"The world of {title}."
    if (work or {}).get("background"):
        world += "\n\n" + _first(work["background"], 900)
    npcs = []
    for c in characters:
        desc = _first(c.get("intro") or c.get("background") or "", 700)
        if not desc:
            continue
        npcs.append({"name": _name(c["title"]), "description": desc,
                     "personality": _first(c.get("personality") or "", 500),
                     "appearance": {"extra": _first(c.get("appearance") or "", 300)} if c.get("appearance") else {},
                     "relationship": 0})
    entries = []
    for i, p in enumerate(lore, 1):
        text = _first(p.get("intro") or "", 900)
        if p.get("abilities") and len(text) < 500:
            text += "\n" + _first(p["abilities"], 400)
        if text:
            name = _name(p["title"])
            entries.append({"id": i, "name": name, "keys": list(dict.fromkeys([name, p["title"]])), "content": text,
                            "enabled": True})
    for c in npcs:  # characters can be looked up by name too, so the Aedo knows them before they appear
        if c["name"] and c["description"]:
            entries.append({"id": len(entries) + 1, "name": c["name"], "keys": [c["name"], c["name"].split()[0]],
                            "content": f"{c['name']}: {_first(c['description'], 400)}", "enabled": True})
    return {
        "name": title, "mode": "gm_world", "kind": "roleplay", "language": language or "",
        "description": f"A story in the world of {title} (researched on {sitename}).",
        "world": world, "tone": f"Faithful to the tone, rules and characters of {title}.",
        "opening_message": "", "npcs": npcs, "lorebook": {"entries": entries},
        "fixed_facts": f"The world, its rules and its characters follow {title} as described in the lorebook.",
    }


def research_notes(sitename: str, card: dict) -> str:
    """A short note for the Muse's talk, so she knows what was found."""
    lines = [f"📚 Research from {sitename}:", f"World: {_first(card.get('world', ''), 500)}"]
    if card.get("npcs"):
        lines.append("Characters: " + "; ".join(f"{n['name']} ({_first(n['description'], 90)})" for n in card["npcs"][:20]))
    lore = [e["name"] for e in (card.get("lorebook") or {}).get("entries", []) if e["name"] not in {n["name"] for n in card.get("npcs", [])}]
    if lore:
        lines.append("Lore: " + ", ".join(lore[:30]))
    return truncate("\n".join(lines), 3000)


async def research(fetch: FetchJson, api: str, sitename: str, work: str, characters: list[str], lore: list[str],
                   language: str = ""):
    """Read the chosen pages and yield progress, then the draft card."""
    chosen = [t for t in characters if str(t).strip()][:MAX_PAGES]
    picked_lore = [t for t in lore if str(t).strip()][: max(0, MAX_PAGES - len(chosen))]
    if not chosen and not picked_lore:
        raise ResearchError("Tick at least one character or lore page.")
    total = len(chosen) + len(picked_lore) + (1 if work else 0)
    done = 0
    work_page = None
    if work:
        try:
            work_page = await read_page(fetch, api, work)
        except Exception:
            work_page = None
        done += 1
        yield {"type": "progress", "step": f"Reading {work} ({done}/{total})"}
    pages_c, pages_l = [], []
    for kind, titles, out in (("character", chosen, pages_c), ("lore", picked_lore, pages_l)):
        for t in titles:
            await asyncio.sleep(GAP)
            try:
                out.append(await read_page(fetch, api, t))
            except Exception:
                pass
            done += 1
            yield {"type": "progress", "step": f"Reading {t} ({done}/{total})"}
    card = build_card(sitename, work_page, pages_c, pages_l, language)
    yield {"type": "card", "card": card, "notes": research_notes(sitename, card)}
