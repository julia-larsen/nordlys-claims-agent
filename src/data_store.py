from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from src.config import DATA_DIR
from src.models import Budget, Grantee

SECTION_HEADING_RE = re.compile(r"^## (S\d+) — (.+)$", re.MULTILINE)


@dataclass(frozen=True)
class HandbookSection:
    section_id: str
    heading: str
    body: str


def _split_handbook(text: str) -> dict[str, HandbookSection]:
    matches = list(SECTION_HEADING_RE.finditer(text))
    sections: dict[str, HandbookSection] = {}
    for i, m in enumerate(matches):
        section_id, heading = m.group(1), m.group(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[section_id] = HandbookSection(section_id, heading, text[start:end].strip())
    return sections


@lru_cache(maxsize=1)
def load_handbook() -> dict[str, HandbookSection]:
    text = (DATA_DIR / "policy_handbook.md").read_text()
    return _split_handbook(text)


@lru_cache(maxsize=1)
def load_grantees() -> dict[str, Grantee]:
    raw = json.loads((DATA_DIR / "grantees.json").read_text())
    return {g["grantee_id"]: Grantee.model_validate(g) for g in raw}


@lru_cache(maxsize=1)
def load_budgets() -> dict[str, Budget]:
    raw = json.loads((DATA_DIR / "budgets.json").read_text())
    return {b["budget_code"]: Budget.model_validate(b) for b in raw}


@lru_cache(maxsize=1)
def load_fx_rates() -> dict[str, dict[str, float]]:
    return json.loads((DATA_DIR / "fx_rates.json").read_text())


@lru_cache(maxsize=1)
def load_claims() -> list[dict]:
    return json.loads((DATA_DIR / "claims.json").read_text())


def claims_by_id() -> dict[str, dict]:
    return {c["claim_id"]: c for c in load_claims()}
