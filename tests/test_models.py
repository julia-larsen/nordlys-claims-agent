import pytest
from pydantic import ValidationError

from src.models import DecisionSubmission


def test_escalate_requires_null_amount():
    with pytest.raises(ValidationError):
        DecisionSubmission(
            claim_id="C-001",
            decision="escalate",
            reimbursable_eur=100.0,
            cited_sections=["S8"],
            reasoning="fx gap",
        )
    DecisionSubmission(
        claim_id="C-001",
        decision="escalate",
        reimbursable_eur=None,
        cited_sections=["S8"],
        reasoning="fx gap",
    )


def test_approve_requires_amount():
    with pytest.raises(ValidationError):
        DecisionSubmission(
            claim_id="C-001",
            decision="approve",
            reimbursable_eur=None,
            cited_sections=["S3"],
            reasoning="ok",
        )


def test_unknown_section_rejected():
    with pytest.raises(ValidationError):
        DecisionSubmission(
            claim_id="C-001",
            decision="approve",
            reimbursable_eur=50.0,
            cited_sections=["S99"],
            reasoning="ok",
        )


def test_empty_citations_rejected():
    with pytest.raises(ValidationError):
        DecisionSubmission(
            claim_id="C-001",
            decision="reject",
            reimbursable_eur=0.0,
            cited_sections=[],
            reasoning="no",
        )
