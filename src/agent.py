from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import litellm
from pydantic import ValidationError

from src.config import DEFAULT_MAX_TOKENS, MAX_STEPS
from src.models import DecisionSubmission
from src.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from src.schemas import ALL_SCHEMAS
from src.tools import (
    convert_to_eur,
    get_handbook_section,
    lookup_budget,
    lookup_grantee,
    search_handbook,
)
from src.trajectory_log import TrajectoryLogger

TOOL_FUNCS: dict[str, Callable[..., Any]] = {
    "search_handbook": search_handbook,
    "get_handbook_section": get_handbook_section,
    "lookup_grantee": lookup_grantee,
    "lookup_budget": lookup_budget,
    "convert_to_eur": convert_to_eur,
}


class StepLimitExceeded(Exception):
    pass


@dataclass
class AgentResult:
    claim_id: str
    decision: Optional[DecisionSubmission]
    steps: int
    total_cost_eur: float
    error: Optional[str]


def _dispatch_tool_call(call: Any) -> dict:
    name = call.function.name
    if name not in TOOL_FUNCS:
        return {"error": f"unknown tool: {name!r}"}
    try:
        args = json.loads(call.function.arguments)
    except json.JSONDecodeError as e:
        return {"error": f"malformed arguments (not valid JSON): {e}"}
    try:
        result = TOOL_FUNCS[name](**args)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    return {"result": result}


def _tool_message(call: Any, payload: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": call.id,
        "content": json.dumps(payload, default=str),
    }


def run_agent(
    claim: dict,
    model: str,
    logger: TrajectoryLogger,
    max_steps: int = MAX_STEPS,
    temperature: float = 0.0,
) -> AgentResult:
    claim_id = claim["claim_id"]
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(claim, default=str)},
    ]

    total_cost = 0.0
    for step in range(1, max_steps + 1):
        start = time.monotonic()
        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                tools=ALL_SCHEMAS,
                tool_choice="auto",
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=temperature,
            )
        except Exception as e:
            error = f"llm_call_failed: {type(e).__name__}: {e}"
            logger.log_step(
                claim_id=claim_id,
                step=step,
                prompt_version=PROMPT_VERSION,
                model=model,
                latency_ms=(time.monotonic() - start) * 1000,
                error=error,
            )
            logger.log_episode_end(
                claim_id=claim_id,
                decision=None,
                reimbursable_eur=None,
                cited_sections=[],
                steps=step,
                total_cost_eur=total_cost,
                error=error,
            )
            return AgentResult(claim_id, None, step, total_cost, error)

        latency_ms = (time.monotonic() - start) * 1000
        usage = getattr(response, "usage", None)
        cost = litellm.completion_cost(response)
        total_cost += cost
        message = response.choices[0].message
        messages.append(message.model_dump())

        tool_calls = message.tool_calls or []

        logger.log_step(
            claim_id=claim_id,
            step=step,
            prompt_version=PROMPT_VERSION,
            model=model,
            latency_ms=latency_ms,
            tokens_in=getattr(usage, "prompt_tokens", None),
            tokens_out=getattr(usage, "completion_tokens", None),
            cost_eur=cost,
            assistant_content=message.content,
            tool_calls=[
                {"name": c.function.name, "arguments": c.function.arguments}
                for c in tool_calls
            ],
        )

        if not tool_calls:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You must respond by calling a tool, or by calling "
                        "submit_decision if you are ready to finish. Plain text "
                        "responses are not accepted."
                    ),
                }
            )
            logger.log_step(
                claim_id=claim_id,
                step=step,
                prompt_version=PROMPT_VERSION,
                model=model,
                latency_ms=0.0,
                error="no_tool_call",
            )
            continue

        decision_result: Optional[DecisionSubmission] = None
        for call in tool_calls:
            if call.function.name == "submit_decision":
                try:
                    args = json.loads(call.function.arguments)
                    decision_result = DecisionSubmission.model_validate(args)
                    messages.append(_tool_message(call, {"result": "accepted"}))
                except (json.JSONDecodeError, ValidationError) as e:
                    messages.append(
                        _tool_message(call, {"error": f"invalid submission: {e}"})
                    )
                    logger.log_step(
                        claim_id=claim_id,
                        step=step,
                        prompt_version=PROMPT_VERSION,
                        model=model,
                        latency_ms=0.0,
                        tool_calls=[{"name": "submit_decision", "error": str(e)}],
                        error="invalid_submission",
                    )
            else:
                payload = _dispatch_tool_call(call)
                messages.append(_tool_message(call, payload))
                if "error" in payload:
                    logger.log_step(
                        claim_id=claim_id,
                        step=step,
                        prompt_version=PROMPT_VERSION,
                        model=model,
                        latency_ms=0.0,
                        tool_calls=[
                            {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                                "error": payload["error"],
                            }
                        ],
                        error="tool_error",
                    )

        if decision_result is not None:
            logger.log_episode_end(
                claim_id=claim_id,
                decision=decision_result.decision,
                reimbursable_eur=decision_result.reimbursable_eur,
                cited_sections=decision_result.cited_sections,
                steps=step,
                total_cost_eur=total_cost,
            )
            return AgentResult(claim_id, decision_result, step, total_cost, None)

    logger.log_episode_end(
        claim_id=claim_id,
        decision=None,
        reimbursable_eur=None,
        cited_sections=[],
        steps=max_steps,
        total_cost_eur=total_cost,
        error="step_limit_exceeded",
    )
    return AgentResult(claim_id, None, max_steps, total_cost, "step_limit_exceeded")
