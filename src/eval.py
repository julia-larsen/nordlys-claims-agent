from __future__ import annotations

import argparse
import json
import statistics

from src.config import DATA_DIR, RUNS_DIR

DECISIONS = ["approve", "reject", "escalate"]
PREDICTED_COLUMNS = DECISIONS + ["no_decision"]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def load_episodes(run_id: str) -> dict[str, dict]:
    path = RUNS_DIR / f"{run_id}.jsonl"
    episodes: dict[str, dict] = {}
    steps_by_claim: dict[str, list[dict]] = {}
    for line in path.read_text().splitlines():
        e = json.loads(line)
        cid = e["claim_id"]
        if e["event"] == "episode_end":
            episodes[cid] = e
        else:
            steps_by_claim.setdefault(cid, []).append(e)
    for cid, ep in episodes.items():
        ep["_steps"] = steps_by_claim.get(cid, [])
    return episodes


def load_labels(final: bool) -> dict[str, dict]:
    if final:
        path = DATA_DIR / "labels_holdout.json.locked"
    else:
        path = DATA_DIR / "labels_dev.json"
    return json.loads(path.read_text())


def score(episodes: dict[str, dict], labels: dict[str, dict]) -> dict:
    confusion = {t: {p: 0 for p in PREDICTED_COLUMNS} for t in DECISIONS}
    per_class_total = {d: 0 for d in DECISIONS}
    per_class_correct = {d: 0 for d in DECISIONS}
    correct = 0
    scored_n = 0

    amount_errors: list[float] = []
    exact_amount_matches = 0
    amount_n = 0

    citation_recall_hits = 0
    citation_exact_hits = 0
    citation_n = 0

    steps_list: list[int] = []
    cost_list: list[float] = []
    tool_error_claims = 0
    step_limit_claims = 0
    missing_lookup_grantee_claims = 0
    no_decision_claims = 0

    missing_from_run = 0
    for claim_id, label in labels.items():
        if claim_id not in episodes:
            missing_from_run += 1
            continue
        ep = episodes[claim_id]
        scored_n += 1
        true_decision = label["decision"]
        agent_decision = ep["decision"]
        per_class_total[true_decision] += 1

        if agent_decision in DECISIONS:
            confusion[true_decision][agent_decision] += 1
            if agent_decision == true_decision:
                correct += 1
                per_class_correct[true_decision] += 1
        else:
            confusion[true_decision]["no_decision"] += 1
            no_decision_claims += 1

        if true_decision == "approve" and agent_decision == "approve":
            amount_n += 1
            true_amt = label["reimbursable_eur"]
            agent_amt = ep["reimbursable_eur"] or 0.0
            err = abs(true_amt - agent_amt)
            amount_errors.append(err)
            if round(true_amt, 2) == round(agent_amt, 2):
                exact_amount_matches += 1

        citation_n += 1
        label_sections = set(label["applied_rules"])
        agent_sections = set(ep["cited_sections"])
        if label_sections <= agent_sections:
            citation_recall_hits += 1
        if label_sections == agent_sections:
            citation_exact_hits += 1

        steps_list.append(ep["steps"])
        cost_list.append(ep["total_cost_eur"])
        if ep.get("error") == "step_limit_exceeded":
            step_limit_claims += 1
        if any(s.get("error") == "tool_error" for s in ep["_steps"]):
            tool_error_claims += 1
        called_lookup_grantee = any(
            tc.get("name") == "lookup_grantee"
            for s in ep["_steps"]
            for tc in s.get("tool_calls", [])
        )
        if not called_lookup_grantee:
            missing_lookup_grantee_claims += 1

    return {
        "n_scored": scored_n,
        "n_missing_from_run": missing_from_run,
        "decision_accuracy": correct / scored_n if scored_n else 0.0,
        "decided_n": scored_n - no_decision_claims,
        "accuracy_given_decided": (
            correct / (scored_n - no_decision_claims) if (scored_n - no_decision_claims) else None
        ),
        "per_class_recall": {
            d: (per_class_correct[d] / per_class_total[d] if per_class_total[d] else None)
            for d in DECISIONS
        },
        "confusion_matrix": confusion,
        "no_decision_rate": no_decision_claims / scored_n if scored_n else None,
        "amount_n": amount_n,
        "amount_exact_match_rate": exact_amount_matches / amount_n if amount_n else None,
        "amount_mae_eur": statistics.mean(amount_errors) if amount_errors else None,
        "citation_recall_rate": citation_recall_hits / citation_n if citation_n else None,
        "citation_exact_match_rate": citation_exact_hits / citation_n if citation_n else None,
        "steps_median": statistics.median(steps_list) if steps_list else None,
        "steps_p90": percentile([float(s) for s in steps_list], 0.9),
        "tool_error_claim_rate": tool_error_claims / scored_n if scored_n else None,
        "step_limit_hit_rate": step_limit_claims / scored_n if scored_n else None,
        "missing_lookup_grantee_rate": missing_lookup_grantee_claims / scored_n if scored_n else None,
        "cost_p50_eur": percentile(cost_list, 0.5),
        "cost_p90_eur": percentile(cost_list, 0.9),
        "cost_total_eur": sum(cost_list),
    }


def print_report(metrics: dict, run_id: str, final: bool) -> None:
    label_set = "HOLDOUT" if final else "dev"
    print(
        f"=== {run_id} scored on {label_set} "
        f"(n={metrics['n_scored']}, missing_from_run={metrics['n_missing_from_run']}) ==="
    )
    print(f"decision accuracy: {metrics['decision_accuracy']:.3f}")
    print(
        f"accuracy given the agent reached a decision: {metrics['accuracy_given_decided']} "
        f"(n={metrics['decided_n']})"
    )
    print(f"no_decision_rate (crashed/step-limited before submitting): {metrics['no_decision_rate']:.3f}")
    print(f"per-class recall:  {metrics['per_class_recall']}")
    print("confusion matrix (rows=true, cols=predicted; no_decision = crashed/step-limited):")
    for t in DECISIONS:
        print(
            f"  {t:>9}: "
            + " ".join(f"{p}={metrics['confusion_matrix'][t][p]}" for p in PREDICTED_COLUMNS)
        )
    print(
        f"amount (n={metrics['amount_n']}): exact_match_rate="
        f"{metrics['amount_exact_match_rate']}, MAE_eur={metrics['amount_mae_eur']}"
    )
    print(
        f"citations: recall_rate={metrics['citation_recall_rate']:.3f}, "
        f"exact_match_rate={metrics['citation_exact_match_rate']:.3f}"
    )
    print(
        f"trajectory: steps median={metrics['steps_median']} p90={metrics['steps_p90']:.1f}, "
        f"tool_error_claim_rate={metrics['tool_error_claim_rate']:.3f}, "
        f"step_limit_hit_rate={metrics['step_limit_hit_rate']:.3f}, "
        f"missing_lookup_grantee_rate={metrics['missing_lookup_grantee_rate']:.3f}"
    )
    print(
        f"cost eur: p50={metrics['cost_p50_eur']:.5f} p90={metrics['cost_p90_eur']:.5f} "
        f"total={metrics['cost_total_eur']:.4f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--final", action="store_true", help="score against the locked holdout set")
    args = parser.parse_args()

    episodes = load_episodes(args.run)
    labels = load_labels(final=args.final)
    metrics = score(episodes, labels)
    print_report(metrics, args.run, args.final)


if __name__ == "__main__":
    main()
