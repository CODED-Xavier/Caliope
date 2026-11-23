"""Translating story text with the story model (Calíope's own engine): an opening, a card, an adventure.

The text is cut at paragraph breaks into pieces the model handles well, each translated on its own; markdown,
picture tags ([[show: …]]), speaker prefixes (**[Lilia]:**) and the names of people and places stay as they are.
A piece the model fails on stays in the original language, so a translation never loses text.
"""
from __future__ import annotations

import re

LANGS = {"pt-BR": "Brazilian Portuguese", "en": "English"}
PIECE = 1400  # characters per call: about 400 tokens in, 500 out

PROMPT = (
    "Translate the text below into {lang}. Rules:\n"
    "- Keep the meaning, tone and paragraph breaks; write naturally, as a {lang} novelist would.\n"
    "- Keep EXACTLY as they are: markdown (*, **, #, >, lists), anything inside [[ ]], speaker labels like **[Name]:**, "
    "names of people, places, houses, techniques and spells, numbers and dice (2d6, DC 13).\n"
    "- Output only the translation, with no notes, no quotes around it and no preface.\n\n"
    "TEXT:\n{text}"
)


def pieces(text: str, size: int = PIECE) -> list[str]:
    """Cut at blank lines (or single lines when a paragraph is huge) into pieces of about `size` characters."""
    paras = re.split(r"(\n\s*\n)", text)
    out, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > size and cur.strip():
            out.append(cur)
            cur = ""
        if len(p) > size * 1.5:  # one enormous paragraph: by lines, then by sentences
            for part in re.split(r"(?<=[.!?…])\s+|\n", p):
                if len(cur) + len(part) > size and cur.strip():
                    out.append(cur)
                    cur = ""
                cur += part + " "
        else:
            cur += p
    if cur.strip():
        out.append(cur)
    return out


def _clean(answer: str, original: str) -> str:
    answer = (answer or "").strip()
    answer = re.sub(r"^(?:here is|aqui está|tradução|translation)[^\n]*:\s*\n", "", answer, flags=re.I)
    if answer.startswith('"') and answer.endswith('"') and not original.strip().startswith('"'):
        answer = answer[1:-1]
    # a reply far too short lost text (or refused): keep the original piece instead
    return answer if len(answer) > len(original.strip()) * 0.45 else original.strip()


async def translate(llm, text: str, lang: str = "pt-BR") -> str:
    if not str(text or "").strip() or lang not in LANGS:
        return text
    done = []
    for piece in pieces(text):
        if not piece.strip():
            done.append(piece)
            continue
        try:
            answer = await llm.chat([{"role": "user", "content": PROMPT.format(lang=LANGS[lang], text=piece.strip())}],
                                    max_tokens=max(300, len(piece) // 2), temperature=0.2)
        except Exception:  # noqa: BLE001 - the model is busy or down: this piece stays in the original language
            answer = piece
        lead = re.match(r"^\s*", piece).group(0)
        trail = re.search(r"\s*$", piece).group(0)
        done.append(lead + _clean(answer, piece) + trail)
    return "".join(done)


# --------------------------------------------------------------------------- whole cards
# Text fields of a card that are names, ids, links, keywords or app settings: never translated
SKIP_KEYS = {"name", "id", "keys", "secondary_keys", "url", "default", "src", "image", "source", "type", "kind", "mode",
             "route", "label", "pictures_folder", "language", "slug", "covers", "tags", "creator", "version", "mood",
             "post_history", "example_messages", "creator_notes", "systems", "features", "calendar", "currency",
             "sheet_template", "rulebooks", "skills", "player", "species", "resources", "abilities", "focus", "maps",
             "monsters", "enemies", "token", "file", "folder", "picture", "pictures", "portraits", "race", "hair", "eyes"}
MIN_LEN = 25


def texts_of(obj, path=()) -> list[tuple[tuple, str]]:
    """Every story text of a card (paths into its JSON) worth translating."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in SKIP_KEYS:
                continue
            out += texts_of(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += texts_of(v, path + (i,))
    elif isinstance(obj, str) and len(obj.strip()) >= MIN_LEN and " " in obj.strip() and not obj.startswith(("/api/", "http")):
        out.append((path, obj))
    return out


def put(obj, path: tuple, value) -> None:
    for p in path[:-1]:
        obj = obj[p]
    obj[path[-1]] = value


async def translate_keys(llm, keys: list[str], lang: str) -> list[str]:
    """A lore entry's trigger words plus their translation (names stay; both languages then wake the entry)."""
    try:
        answer = await llm.chat([{"role": "user", "content": (
            f"Translate each of these keywords into {LANGS[lang]}. Keep names of people and places unchanged. "
            f"Answer with the keywords only, separated by commas, in the same order.\n\n{', '.join(keys)}")}],
            max_tokens=200, temperature=0.1)
    except Exception:  # noqa: BLE001 - the English keywords stay
        return keys
    new = [w.strip(" .\"'\n") for w in str(answer).split(",") if 0 < len(w.strip()) <= 40]
    return list(dict.fromkeys(keys + new))[:40]


JOBS: dict[int, dict] = {}  # card id -> {"status", "done", "total", "new_id", "error", "cancel"}


async def translate_card(svc, card_id: int, lang: str = "pt-BR") -> None:
    """A translated copy of a card ("Lumencia Academy RPG (Português)"), its texts one by one; the original stays."""
    import copy
    import logging
    job = JOBS[card_id]
    try:
        card = svc.scenarios.get(card_id)
        data = copy.deepcopy(card["data"])
        todo = texts_of(data)
        job["total"] = (sum(len(pieces(t)) for _, t in todo) or 1) + len((data.get("lorebook") or {}).get("entries") or [])
        for path, text in todo:
            if job.get("cancel"):
                job["status"] = "cancelled"
                return
            done = []
            for piece in pieces(text):
                done.append(await translate(svc.llm, piece, lang) if piece.strip() else piece)
                job["done"] += 1
            put(data, path, "".join(done))
        for entry in (data.get("lorebook") or {}).get("entries") or []:  # the trigger words in the new language too
            if job.get("cancel"):
                job["status"] = "cancelled"
                return
            keys = [k for k in entry.get("keys") or [] if isinstance(k, str)]
            if keys:
                entry["keys"] = await translate_keys(svc.llm, keys, lang)
            job["done"] += 1
        suffix = " (Português)" if lang == "pt-BR" else " (English)"
        new = svc.scenarios.create({**data, "name": (card["name"] + suffix)[:100], "language": lang})
        job.update(status="done", new_id=new["id"], done=job["total"])
    except Exception as exc:  # noqa: BLE001 - shown on the card; the original card is never touched
        logging.getLogger("rpg").exception("card translation failed")
        job.update(status="error", error=str(exc)[:200])
