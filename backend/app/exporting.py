"""Export a game as a Markdown file you can read anywhere."""
from __future__ import annotations

import re
from datetime import datetime

_TAG = re.compile(r"^\s*\[\[\s*show\s*:[^\]]*\]\]\s*$", re.M | re.I)


def export_markdown(conv: dict, messages: list[dict], state: dict) -> str:
    player = state.get("player", {}).get("name") or "You"
    scenario = conv.get("scenario") or {}
    lines = [f"# {conv['title']}", "",
             f"*{scenario.get('name', '')} · exported {datetime.now().strftime('%Y-%m-%d %H:%M')}*", ""]
    if conv.get("summary"):
        lines += ["> **Story so far:** " + conv["summary"].replace("\n", " "), ""]
    for m in messages:
        text = _TAG.sub("", m["content"]).strip()
        text = re.sub(r"\n{3,}", "\n\n", text)
        if m["role"] == "user":
            lines += [f"**{player}:** {text}", ""]
        else:
            lines += [text, "", "---", ""]
    return "\n".join(lines).rstrip() + "\n"
