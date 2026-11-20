"""Buying and paying done by the app: the gold is counted by code, not guessed by the AI.

When a reply lists things for sale with prices ("a coil of rope (1 gold)", "the room is 5 crowns a night"), the app
shows buy buttons. Buying checks your money, takes it, puts the item in your bag and tells the GM what happened.
Paying someone works the same way from the Bag tab. The tracker leaves money and items alone on those turns, so
nothing is counted twice.
"""
from __future__ import annotations

import re

from .state import _norm_item
from .util import as_int, truncate

BUY_MARK, PAY_MARK = "\U0001F6D2", "\U0001F4B0"
MAX_OFFERS = 6
_CURRENCY = r"(?:gold(?: pieces?| coins?)?|gp|gc|coins?|crowns?|marks?|ouro|pe[çc]as de ouro|moedas(?: de ouro)?|coroas?{extra})"
_SKIP = {"it", "that", "this", "those", "these", "them", "everything", "all", "total", "price", "cost", "you", "he", "she", "they",
         "isso", "isto", "tudo", "total", "preço"}
_LEAD = {"and", "or", "plus", "also", "a", "an", "the", "some", "buy", "sell", "sells", "offer", "offers", "has", "have", "got",
         "shows", "e", "ou", "um", "uma", "o", "os", "as", "uns", "umas", "compra", "vende", "oferece", "mostra", "tem"}


def _currency_rx(currency: str) -> str:
    extra = ""
    name = (currency or "").strip().lower()
    if name and name not in ("gold", "ouro"):
        extra = "|" + re.escape(name) + "s?"
    return _CURRENCY.replace("{extra}", extra)


def _clean_item(raw: str) -> str:
    item = re.sub(r"[*_\"“”]", "", raw).strip(" ,.;:-–—")
    item = re.split(r"[,;:.!?]\s*", item)[-1]  # only the words right before the price
    words = item.split()[-6:]
    cut = max((i for i, w in enumerate(words) if w.lower() in _LEAD), default=-1)
    if cut < len(words) - 1:
        words = words[cut + 1:]  # "she offers a long sword" -> "long sword"
    return " ".join(words).strip()


def find_offers(reply: str, currency: str = "gold") -> list[dict]:
    """[{'item': 'coil of rope', 'price': 1}] for things the reply sells with a price."""
    cur = _currency_rx(currency)
    patterns = [
        re.compile(rf"([A-Za-zÀ-ÿ][\w'À-ÿ \-]{{1,50}}?)\s*[\(\[]\s*(\d{{1,5}})\s*{cur}\b[^\)\]]{{0,20}}[\)\]]", re.I),
        re.compile(rf"([A-Za-zÀ-ÿ][\w'À-ÿ \-]{{1,50}}?)\s*(?:\bfor\b|\bcosts?\b|\bat\b|\bis\b|\bpor\b|\bcusta\b|:|—|–|-)\s*(\d{{1,5}})\s*{cur}\b", re.I),
    ]
    out: list[dict] = []
    for line in re.split(r"\n+|(?<=[.!?])\s+", reply or ""):
        for rx in patterns:
            for m in rx.finditer(line):
                item, price = _clean_item(m.group(1)), as_int(m.group(2))
                if not item or item.lower() in _SKIP or len(item) < 3 or price <= 0:
                    continue
                if not any(o["item"].lower() == item.lower() for o in out):
                    out.append({"item": truncate(item, 50), "price": price})
                if len(out) >= MAX_OFFERS:
                    return out
    return out


def buy(state: dict, offer: dict, qty: int, currency: str) -> tuple[dict, str]:
    qty = max(1, min(99, int(qty or 1)))
    cost = offer["price"] * qty
    gold = as_int(state.get("gold", 0))
    if cost > gold:
        raise ValueError(f"Not enough {currency}: {offer['item']} costs {cost}, you have {gold}.")
    state["gold"] = gold - cost
    item = _norm_item({"name": offer["item"], "qty": qty})
    have = next((i for i in state["inventory"] if i["name"].lower() == item["name"].lower()), None)
    if have:
        have["qty"] += qty
    else:
        state["inventory"].append(item)
    what = f"{qty} × {offer['item']}" if qty > 1 else offer["item"]
    return state, f"{BUY_MARK} Bought {what} for {cost} {currency} ({currency} left: {state['gold']})."


def pay(state: dict, amount: int, to: str, why: str, currency: str) -> tuple[dict, str]:
    amount = as_int(amount)
    if amount <= 0:
        raise ValueError("Write how much to pay.")
    gold = as_int(state.get("gold", 0))
    if amount > gold:
        raise ValueError(f"Not enough {currency}: you have {gold}.")
    state["gold"] = gold - amount
    to = truncate((to or "").strip(), 60)
    why = truncate((why or "").strip(), 80)
    return state, (f"{PAY_MARK} Paid {amount} {currency}" + (f" to {to}" if to else "") + (f" for {why}" if why else "")
                   + f" ({currency} left: {state['gold']}).")


def is_trade(text: str) -> bool:
    return (text or "").lstrip().startswith((BUY_MARK, PAY_MARK))
