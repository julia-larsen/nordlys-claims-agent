from __future__ import annotations

import re

from src.data_store import load_budgets, load_fx_rates, load_grantees, load_handbook
from src.models import BudgetNotFound, GranteeNotFound, RateUnavailable, UnknownSection

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "the", "is", "are", "of", "on", "in", "to", "for", "and",
    "or", "not", "it", "its", "be", "by", "at", "as", "if", "no",
}


def _tokenize(text: str) -> set[str]:
    words = _WORD_RE.findall(text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _best_excerpt(body: str, query_tokens: set[str], width: int = 220) -> str:
    lower = body.lower()
    best_pos = None
    for token in query_tokens:
        pos = lower.find(token)
        if pos != -1 and (best_pos is None or pos < best_pos):
            best_pos = pos
    if best_pos is None:
        start = 0
    else:
        start = max(0, best_pos - 40)
    excerpt = body[start : start + width].strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if start + width < len(body) else ""
    return prefix + excerpt + suffix


def search_handbook(query: str) -> list[dict]:
    query_tokens = _tokenize(query)
    scored: list[tuple[int, str]] = []
    for section_id, section in load_handbook().items():
        section_tokens = _tokenize(section.heading + " " + section.body)
        overlap = len(query_tokens & section_tokens)
        if overlap > 0:
            scored.append((overlap, section_id))
    scored.sort(key=lambda t: (-t[0], t[1]))

    hits = []
    for _, section_id in scored[:3]:
        section = load_handbook()[section_id]
        excerpt = _best_excerpt(section.body, query_tokens)
        hits.append({"section_id": section_id, "heading": section.heading, "excerpt": excerpt})
    return hits


def get_handbook_section(section_id: str) -> str:
    sections = load_handbook()
    if section_id not in sections:
        raise UnknownSection(f"no such section: {section_id!r}")
    section = sections[section_id]
    return f"## {section.section_id} — {section.heading}\n\n{section.body}"


def lookup_grantee(grantee_id: str) -> dict:
    grantees = load_grantees()
    if grantee_id not in grantees:
        raise GranteeNotFound(f"no such grantee: {grantee_id!r}")
    return grantees[grantee_id].model_dump()


def lookup_budget(budget_code: str) -> dict:
    budgets = load_budgets()
    if budget_code not in budgets:
        raise BudgetNotFound(f"no such budget code: {budget_code!r}")
    return budgets[budget_code].model_dump()


def convert_to_eur(amount: float, currency: str, expense_date: str) -> float:
    currency = currency.upper()
    if currency == "EUR":
        return round(amount, 2)
    month = expense_date[:7]
    rates = load_fx_rates()
    if month not in rates or currency not in rates[month]:
        raise RateUnavailable(f"no published {currency} rate for {month}")
    return round(amount * rates[month][currency], 2)
