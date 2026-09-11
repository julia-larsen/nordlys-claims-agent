from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from src.agent import run_agent
from src.config import LARGE_MODEL, MAX_RUN_COST_EUR, MAX_STEPS, RUNS_DIR, SMALL_MODEL
from src.data_store import claims_by_id
from src.trajectory_log import TrajectoryLogger

MODEL_ALIASES = {"small": SMALL_MODEL, "large": LARGE_MODEL}

DEV_IDS = [f"C-{i:03d}" for i in range(1, 21)]
HOLDOUT_IDS = [f"C-{i:03d}" for i in range(21, 61)]


def resolve_claim_ids(claim_set: str) -> list[str]:
    if claim_set == "dev":
        return DEV_IDS
    if claim_set == "holdout":
        return HOLDOUT_IDS
    if claim_set == "all":
        return DEV_IDS + HOLDOUT_IDS
    return [claim_set]


def run_batch(
    claim_ids: list[str],
    model: str,
    run_id: str,
    max_steps: int = MAX_STEPS,
    max_run_cost_eur: float = MAX_RUN_COST_EUR,
    temperature: float = 0.0,
) -> None:
    claims = claims_by_id()
    log_path = RUNS_DIR / f"{run_id}.jsonl"
    logger = TrajectoryLogger(log_path)
    total_cost = 0.0
    try:
        for claim_id in claim_ids:
            if total_cost >= max_run_cost_eur:
                print(
                    f"ABORT: run cost {total_cost:.4f} EUR reached ceiling "
                    f"{max_run_cost_eur} EUR before claim {claim_id}",
                    file=sys.stderr,
                )
                break
            claim = claims[claim_id]
            result = run_agent(
                claim, model=model, logger=logger, max_steps=max_steps, temperature=temperature
            )
            total_cost += result.total_cost_eur
            print(
                f"{claim_id}: decision={result.decision.decision if result.decision else None} "
                f"steps={result.steps} cost={result.total_cost_eur:.5f} error={result.error}"
            )
    finally:
        logger.close()
    print(f"\nrun_id={run_id} total_cost_eur={total_cost:.4f} log={log_path}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--claims", default="dev", help="'dev', 'holdout', 'all', or a single claim id")
    parser.add_argument("--model", default="small", help="'small', 'large', or a raw litellm model string")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS)
    parser.add_argument("--max-run-cost-eur", type=float, default=MAX_RUN_COST_EUR)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()

    model = MODEL_ALIASES.get(args.model, args.model)
    claim_ids = resolve_claim_ids(args.claims)
    run_batch(
        claim_ids,
        model=model,
        run_id=args.run_id,
        max_steps=args.max_steps,
        max_run_cost_eur=args.max_run_cost_eur,
        temperature=args.temperature,
    )


if __name__ == "__main__":
    main()
