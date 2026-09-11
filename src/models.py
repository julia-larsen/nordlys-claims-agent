from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, field_validator, model_validator

from src.config import VALID_SECTIONS


class Grantee(BaseModel):
    grantee_id: str
    name: str
    grade: Literal["junior", "senior", "principal"]
    home_country: str
    grant_type: Literal["travel", "field"]


class Budget(BaseModel):
    budget_code: str
    label: str
    remaining_eur: float


class HandbookHit(BaseModel):
    section_id: str
    heading: str
    excerpt: str


class UnknownSection(Exception):
    pass


class RateUnavailable(Exception):
    pass


class GranteeNotFound(Exception):
    pass


class BudgetNotFound(Exception):
    pass


class DecisionSubmission(BaseModel):
    claim_id: str
    decision: Literal["approve", "reject", "escalate"]
    reimbursable_eur: Optional[float] = None
    cited_sections: list[str]
    reasoning: str

    @field_validator("cited_sections")
    @classmethod
    def sections_must_be_known(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("cited_sections must not be empty")
        unknown = [s for s in v if s not in VALID_SECTIONS]
        if unknown:
            raise ValueError(f"unknown section id(s): {unknown}")
        return v

    @model_validator(mode="after")
    def amount_matches_decision(self) -> "DecisionSubmission":
        if self.decision == "escalate":
            if self.reimbursable_eur is not None:
                raise ValueError("reimbursable_eur must be None when decision is 'escalate'")
        else:
            if self.reimbursable_eur is None:
                raise ValueError(
                    f"reimbursable_eur is required when decision is '{self.decision}'"
                )
            if self.reimbursable_eur < 0:
                raise ValueError("reimbursable_eur must not be negative")
        return self
