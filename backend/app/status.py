"""The INFO / status block some cards ask the AI to write at the end of a reply.

The app hides it from the story text, shows it in the Status tab, keeps only the newest one in the
history it sends to the model (older ones would waste hundreds of tokens), and asks for a new one only
every few replies.
"""
from __future__ import annotations

import re

# A line that is just INFO (optionally **INFO** or [INFO]) starts the block; it runs to the end of the text.
_START = re.compile(r"(?m)^[ \t]*(?:\*\*|\[)?INFO(?:\*\*|\])?[ \t]*$")
_END_MARK = re.compile(r"\s*<END>\s*$")


def split_status(text: str) -> tuple[str, str | None]:
    """(text without the status block, the block or None). Only the LAST INFO line counts."""
    matches = list(_START.finditer(text or ""))
    if not matches:
        return text or "", None
    m = matches[-1]
    block = _END_MARK.sub("", text[m.start():]).strip()
    # Story text after the block ("How do you answer Professor Artemis?") goes back to the story: after a blank
    # line, a paragraph without "Label:" lines is not part of the status.
    paras = re.split(r"\n\s*\n", block)
    keep, tail = [paras[0]], []
    for para in paras[1:]:
        if tail or not re.search(r"^\s*[-*]?\s*[^:\n]{1,40}:", para, re.M):
            tail.append(para)
        else:
            keep.append(para)
    story = text[: m.start()].rstrip()
    if tail:
        story = (story + "\n\n" + "\n\n".join(tail)).strip()
    return story, "\n\n".join(keep)


def split_template(card_text: str) -> tuple[str, str | None]:
    """Split card rules into (rules, INFO template). Works on the card's post-history text."""
    return split_status(card_text)


def keep_latest_status(history: list[dict]) -> list[dict]:
    """Copy of `history` where only the newest assistant status block is kept."""
    out = [dict(h) for h in history]
    last = None
    for i in range(len(out) - 1, -1, -1):
        if out[i]["role"] == "assistant" and split_status(out[i]["content"])[1]:
            last = i
            break
    for i, h in enumerate(out):
        if h["role"] == "assistant" and i != last:
            h["content"] = split_status(h["content"])[0]
    return out
