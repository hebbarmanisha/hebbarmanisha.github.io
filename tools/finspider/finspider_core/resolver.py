"""Turn a company name (or ticker) into a Yahoo Finance symbol."""
from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from .errors import TickerNotFound, UserAborted

log = logging.getLogger(__name__)

_SUFFIXES = {"ltd", "limited", "inc", "corp", "corporation", "co", "company", "plc", "the", "and", "&"}


@dataclass
class Candidate:
    symbol: str
    name: str
    exchange: str
    sector: str = ""
    industry: str = ""


def _tokens(s: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", s.lower())
    return [w for w in words if w not in _SUFFIXES]


def _company_key(name: str) -> str:
    return " ".join(_tokens(name))


def name_matches(query: str, name: str) -> bool:
    """True if every word of the query appears as a whole word in the name."""
    q, n = _tokens(query), set(_tokens(name))
    return bool(q) and all(w in n for w in q)


def search_candidates(query: str, max_results: int = 8) -> list[Candidate]:
    import yfinance as yf
    try:
        res = yf.Search(query, max_results=max_results, news_count=0)
        quotes = res.quotes or []
    except Exception as e:
        raise TickerNotFound(f"Ticker search failed for '{query}': {e}") from e
    out = []
    for q in quotes:
        if q.get("quoteType") != "EQUITY":
            continue
        out.append(Candidate(
            symbol=q.get("symbol", ""),
            name=q.get("longname") or q.get("shortname") or q.get("symbol", ""),
            exchange=q.get("exchange", ""),
            sector=q.get("sector", "") or "",
            industry=q.get("industry", "") or "",
        ))
    return out


def pick_listing(cands: list[Candidate], preferred_exchanges: list[str]) -> Candidate:
    """Among listings of the same company, pick the preferred exchange."""
    rank = {ex: i for i, ex in enumerate(preferred_exchanges)}
    return sorted(cands, key=lambda c: rank.get(c.exchange, len(rank)))[0]


def group_by_company(cands: list[Candidate]) -> dict[str, list[Candidate]]:
    groups: dict[str, list[Candidate]] = {}
    for c in cands:
        groups.setdefault(_company_key(c.name), []).append(c)
    return groups


def choose(query: str, cands: list[Candidate], preferred_exchanges: list[str],
           ask: Optional[Callable[[list[Candidate]], Candidate]] = None) -> Candidate:
    """Resolve to one candidate, asking the user only when it is genuinely ambiguous."""
    if not cands:
        raise TickerNotFound(f"No listed company found for '{query}'. Try the exact name or pass --ticker.")
    groups = group_by_company(cands)
    matching = {k: v for k, v in groups.items() if any(name_matches(query, c.name) for c in v)}
    pool = matching or groups
    if len(pool) == 1:
        return pick_listing(next(iter(pool.values())), preferred_exchanges)
    # Several different companies match: one entry per company, best listing each.
    options = [pick_listing(v, preferred_exchanges) for v in pool.values()]
    if ask is None:
        log.warning("'%s' is ambiguous; picking the top match %s (%s). Use --ticker to choose.",
                    query, options[0].name, options[0].symbol)
        return options[0]
    return ask(options)


def ask_interactively(options: list[Candidate]) -> Candidate:
    print("\nSeveral companies match. Which one did you mean?")
    for i, c in enumerate(options, 1):
        extra = f" - {c.industry}" if c.industry else ""
        print(f"  {i}. {c.name} [{c.symbol}, {c.exchange}]{extra}")
    while True:
        try:
            raw = input(f"Enter 1-{len(options)} (or q to quit): ").strip().lower()
        except EOFError:
            raise UserAborted("No selection made.")
        if raw in ("q", "quit", "exit"):
            raise UserAborted("Cancelled.")
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("Please enter a number from the list.")


def looks_like_ticker(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9&\-]{1,15}(\.[A-Z]{1,3})?", s.strip()))


def resolve(query: str, cfg: dict, interactive: Optional[bool] = None) -> Candidate:
    rcfg = cfg["resolver"]
    if interactive is None:
        interactive = sys.stdin.isatty()
    cands = search_candidates(query, rcfg.get("max_candidates", 8))
    # An exact symbol match (e.g. "INFY.NS") wins outright.
    for c in cands:
        if c.symbol.upper() == query.strip().upper():
            return c
    if not cands and looks_like_ticker(query):
        return Candidate(symbol=query.strip().upper(), name=query.strip().upper(), exchange="")
    return choose(query, cands, rcfg.get("preferred_exchanges", []),
                  ask=ask_interactively if interactive else None)
