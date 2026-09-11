from __future__ import annotations

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_handbook",
            "description": (
                "Keyword search over the 13-section expense policy handbook. "
                "Use this first when you don't know which section governs a "
                "situation. Returns up to 3 hits ranked by keyword overlap, each "
                "with a short excerpt. Follow up with get_handbook_section for "
                "the full text before relying on a rule."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Plain-language search terms, e.g. 'lodging cap' or "
                            "'currency conversion missing rate'."
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_handbook_section",
            "description": (
                "Full text of one handbook section by id. Raises an error if the "
                "section id does not exist (valid ids are S1 through S13)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section_id": {
                        "type": "string",
                        "description": "Section id, e.g. 'S3'.",
                    }
                },
                "required": ["section_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_grantee",
            "description": (
                "Look up a grantee's grade, home country, and grant type. The "
                "grade and grant type affect per-diem caps and uplifts, so call "
                "this before evaluating any per_diem or lodging line."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "grantee_id": {
                        "type": "string",
                        "description": "Grantee id from the claim, e.g. 'G-004'.",
                    }
                },
                "required": ["grantee_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_budget",
            "description": (
                "Look up the remaining euro balance on a budget code. Needed to "
                "check whether the claim total exceeds the budget."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_code": {
                        "type": "string",
                        "description": "Budget code from the claim, e.g. 'BUD-CONF-01'.",
                    }
                },
                "required": ["budget_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_to_eur",
            "description": (
                "Convert an amount to euro using the Foundation's published "
                "monthly rate. Raises an error if no rate is published for that "
                "month; when that happens, do not guess a rate or fall back to "
                "another month — the handbook defines what to do in that case."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "The line item amount, in its original currency.",
                    },
                    "currency": {
                        "type": "string",
                        "description": "ISO currency code of the amount, e.g. 'SEK'. Use 'EUR' if already in euro.",
                    },
                    "expense_date": {
                        "type": "string",
                        "description": (
                            "The date the EXPENSE was INCURRED (the line item's own "
                            "'date' field), in YYYY-MM-DD. This is NOT the claim's "
                            "submitted_on date — conversion uses the rate for the "
                            "month the cost happened, not the month it was filed."
                        ),
                    },
                },
                "required": ["amount", "currency", "expense_date"],
            },
        },
    },
]

SUBMIT_DECISION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_decision",
        "description": (
            "Submit the final decision for this claim and end your turn. Call "
            "this exactly once, only after you have gathered what you need."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "decision": {
                    "type": "string",
                    "enum": ["approve", "reject", "escalate"],
                },
                "reimbursable_eur": {
                    "type": ["number", "null"],
                    "description": (
                        "Total reimbursable amount in euro. Must be null if and "
                        "only if decision is 'escalate'. 0 for a full reject."
                    ),
                },
                "cited_sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Handbook section ids that justify this decision, e.g. "
                        "['S3', 'S6']. Cite every section you actually relied on."
                    ),
                },
                "reasoning": {
                    "type": "string",
                    "description": "One or two sentences for the human reviewer.",
                },
            },
            "required": ["claim_id", "decision", "reimbursable_eur", "cited_sections", "reasoning"],
        },
    },
}

ALL_SCHEMAS = TOOL_SCHEMAS + [SUBMIT_DECISION_SCHEMA]
