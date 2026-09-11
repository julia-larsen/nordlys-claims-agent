from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional


class TrajectoryLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "a")

    def _write(self, record: dict) -> None:
        record.setdefault("ts", time.time())
        self._fh.write(json.dumps(record, default=str) + "\n")
        self._fh.flush()

    def log_step(
        self,
        claim_id: str,
        step: int,
        prompt_version: str,
        model: str,
        latency_ms: float,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        cost_eur: Optional[float] = None,
        assistant_content: Optional[str] = None,
        tool_calls: Optional[list[dict[str, Any]]] = None,
        error: Optional[str] = None,
    ) -> None:
        self._write(
            {
                "event": "step",
                "claim_id": claim_id,
                "step": step,
                "prompt_version": prompt_version,
                "model": model,
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_eur": cost_eur,
                "assistant_content": assistant_content,
                "tool_calls": tool_calls or [],
                "error": error,
            }
        )

    def log_episode_end(
        self,
        claim_id: str,
        decision: Optional[str],
        reimbursable_eur: Optional[float],
        cited_sections: list[str],
        steps: int,
        total_cost_eur: float,
        error: Optional[str] = None,
    ) -> None:
        self._write(
            {
                "event": "episode_end",
                "claim_id": claim_id,
                "decision": decision,
                "reimbursable_eur": reimbursable_eur,
                "cited_sections": cited_sections,
                "steps": steps,
                "total_cost_eur": total_cost_eur,
                "error": error,
            }
        )

    def close(self) -> None:
        self._fh.close()
