import json
from types import SimpleNamespace

from src.agent import run_agent
from src.trajectory_log import TrajectoryLogger

LODGING_CLAIM = {
    "claim_id": "C-TEST",
    "grantee_id": "G-001",
    "budget_code": "BUD-MOBILITY-01",
    "destination_city": "Zurich",
    "submitted_on": "2026-01-10",
    "justification": "Trip to Zurich for a partner site visit.",
    "line_items": [
        {
            "line_id": "C-TEST-L1",
            "date": "2026-01-05",
            "category": "lodging",
            "description": "Hotel in Zurich, 3 nights",
            "amount": 660.0,
            "currency": "EUR",
            "receipt_attached": True,
            "nights": 3,
        }
    ],
}


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict):
        self.id = call_id
        self.type = "function"
        self.function = SimpleNamespace(name=name, arguments=json.dumps(arguments))


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.role = "assistant"
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self):
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in self.tool_calls
            ]
            or None,
        }


class FakeResponse:
    def __init__(self, message: FakeMessage):
        self.choices = [SimpleNamespace(message=message)]
        self.usage = SimpleNamespace(prompt_tokens=50, completion_tokens=20)


def _script(responses):
    it = iter(responses)

    def fake_completion(**kwargs):
        return next(it)

    return fake_completion


def test_agent_loop_applies_per_night_lodging_cap(monkeypatch, tmp_path):
    responses = [
        FakeResponse(FakeMessage(tool_calls=[FakeToolCall("1", "get_handbook_section", {"section_id": "S1"})])),
        FakeResponse(FakeMessage(tool_calls=[FakeToolCall("2", "get_handbook_section", {"section_id": "S3"})])),
        FakeResponse(
            FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "3",
                        "submit_decision",
                        {
                            "claim_id": "C-TEST",
                            "decision": "approve",
                            "reimbursable_eur": 540.0,
                            "cited_sections": ["S1", "S3"],
                            "reasoning": "Zurich is Tier A; cap is 180/night for 3 nights.",
                        },
                    )
                ]
            )
        ),
    ]
    monkeypatch.setattr("src.agent.litellm.completion", _script(responses))
    monkeypatch.setattr("src.agent.litellm.completion_cost", lambda response: 0.001)

    log_path = tmp_path / "test_run.jsonl"
    logger = TrajectoryLogger(log_path)
    result = run_agent(LODGING_CLAIM, model="fake-model", logger=logger, max_steps=5)
    logger.close()

    assert result.error is None
    assert result.decision is not None
    assert result.decision.reimbursable_eur == 540.0
    assert result.steps == 3

    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 4
    events = [json.loads(l) for l in lines]
    assert [e["event"] for e in events] == ["step", "step", "step", "episode_end"]
    assert events[-1]["reimbursable_eur"] == 540.0


def test_agent_loop_recovers_from_tool_error_and_escalates(monkeypatch, tmp_path):
    responses = [
        FakeResponse(
            FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "1", "convert_to_eur", {"amount": 100.0, "currency": "SEK", "expense_date": "2026-02-10"}
                    )
                ]
            )
        ),
        FakeResponse(
            FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "2",
                        "submit_decision",
                        {
                            "claim_id": "C-TEST",
                            "decision": "escalate",
                            "reimbursable_eur": None,
                            "cited_sections": ["S8"],
                            "reasoning": "No published FX rate for February 2026.",
                        },
                    )
                ]
            )
        ),
    ]
    monkeypatch.setattr("src.agent.litellm.completion", _script(responses))
    monkeypatch.setattr("src.agent.litellm.completion_cost", lambda response: 0.001)

    log_path = tmp_path / "test_run.jsonl"
    logger = TrajectoryLogger(log_path)
    result = run_agent(LODGING_CLAIM, model="fake-model", logger=logger, max_steps=5)
    logger.close()

    assert result.decision.decision == "escalate"
    assert result.decision.reimbursable_eur is None

    events = [json.loads(l) for l in log_path.read_text().strip().splitlines()]
    tool_error_events = [e for e in events if e.get("error") == "tool_error"]
    assert len(tool_error_events) == 1
    assert "RateUnavailable" in tool_error_events[0]["tool_calls"][0]["error"]


def test_agent_loop_hits_step_limit(monkeypatch, tmp_path):
    stall = FakeResponse(
        FakeMessage(tool_calls=[FakeToolCall("1", "get_handbook_section", {"section_id": "S1"})])
    )
    monkeypatch.setattr("src.agent.litellm.completion", lambda **kwargs: stall)
    monkeypatch.setattr("src.agent.litellm.completion_cost", lambda response: 0.0005)

    log_path = tmp_path / "test_run.jsonl"
    logger = TrajectoryLogger(log_path)
    result = run_agent(LODGING_CLAIM, model="fake-model", logger=logger, max_steps=3)
    logger.close()

    assert result.error == "step_limit_exceeded"
    assert result.decision is None
    assert result.steps == 3
