# Nordlys Foundation — Claims Triage Agent

An LLM agent that assesses grantee expense claims against a 13-section policy
handbook, plus the harness used to measure whether it works and what it
costs. Built for the Nordlys Agent Engineering Challenge; see `bootstrap/` for
the original prompt and fixture generator.

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Put an API key in `.env` (gitignored; this repo uses Gemini via `litellm`):

```
GEMINI_API_KEY=...
```

Data in `data/` was generated once by `bootstrap/generate_data.py` (fixed
seed) and is committed as-is; it is not regenerated.

## Running it

```
python -m src.runner --claims dev --model small --run-id my_run
python -m src.eval --run my_run
```

`--model` accepts `small` (`gemini/gemini-3.5-flash-lite`), `large`
(`gemini/gemini-3.8-flash`), or any raw `litellm` model string. `--claims`
accepts `dev`, `holdout`, `all`, or a single claim id. Scoring against the
locked holdout set requires `--final` on `src.eval` and is meant to be run
once.

## Results

**Currency correction:** every cost figure below is labeled "€" but was
computed from `litellm.completion_cost()`, which is always denominated in
USD — the pricing tables it draws from (Google's Gemini pricing page
included) are USD-only, and no conversion was applied when these tables were
built. The dollar figures themselves are correct; treat the "€" symbol below
as "$" until these tables are regenerated. At the current rate (~$1 = €0.86,
September 2026), actual euro costs are about 14% lower than shown — e.g. the
holdout run's reported "€2.7268" total is really $2.7268 ≈ €2.35. See [Cost
projection at scale](#cost-projection-at-scale) for figures with the
conversion correctly applied.

### Dev set (n=20), two configurations, prompt v2, max_steps=16

| metric | small (flash-lite) | large (flash) |
|---|---|---|
| decision accuracy | 0.650 | 0.800 |
| **accuracy given the agent reached a decision** | 0.765 (n=17) | **1.000 (n=16)** |
| reject recall | 0.00 | 1.00 |
| escalate recall | 0.50 | 1.00 |
| approve recall | 0.85 | 0.69 |
| amount exact-match (approved, both sides agree) | 0.18 | 0.89 |
| amount MAE (EUR) | 96.46 | 0.11 |
| citation recall (label ⊆ agent) | 0.80 | 0.95 |
| citation exact-match | 0.05 | 0.35 |
| steps median / p90 | 10.5 / 16.0 | 13.5 / 16.0 |
| step-limit hit rate | 0.15 | 0.20 |
| cost/claim p50 | €0.014 | €0.077 |
| cost/claim p90 | €0.019 | €0.110 |
| total run cost | €0.28 | €1.57 |

Confusion matrices (rows = true, cols = predicted; `no_decision` = crashed or
hit the step ceiling before submitting):

**Small**

| true \ pred | approve | reject | escalate | no_decision |
|---|---|---|---|---|
| approve | 11 | 0 | 0 | 2 |
| reject | 3 | 0 | 0 | 0 |
| escalate | 1 | 0 | 2 | 1 |

**Large**

| true \ pred | approve | reject | escalate | no_decision |
|---|---|---|---|---|
| approve | 9 | 0 | 0 | 4 |
| reject | 0 | 3 | 0 | 0 |
| escalate | 0 | 0 | 4 | 0 |

The large model's *only* error type in this sample is `no_decision`
(step-limit). Every claim it actually resolved, it resolved correctly. The
small model has real wrong-decision errors, including the dangerous
direction: it approved every claim that should have been rejected.

### Holdout (n=40), large model, scored once

Scored exactly once, after the configuration decision above was made from
dev-set evidence alone.

| metric | dev (n=20) | holdout (n=40) |
|---|---|---|
| decision accuracy | 0.800 | 0.825 |
| accuracy given the agent reached a decision | 1.000 (n=16) | 1.000 (n=33) |
| reject recall | 1.00 | 1.00 |
| escalate recall | 1.00 | 1.00 |
| approve recall | 0.69 | 0.74 |
| amount exact-match | 0.89 | 0.95 |
| amount MAE (EUR) | 0.11 | 0.03 |
| citation recall | 0.95 | 0.85 |
| citation exact-match | 0.35 | 0.25 |
| step-limit hit rate | 0.20 | 0.175 |
| tool-error claim rate | 0.05 | 0.15 |
| cost/claim p50 | €0.077 | €0.062 |
| total run cost | €1.57 | €2.73 |

Holdout accuracy is not worse than dev — it is marginally higher (82.5% vs
80.0%), and the "accuracy given a decision" result (1.000) holds exactly, now
over a larger sample (n=33 vs n=16). Citation recall and exact-match are both
a bit lower on holdout. None of these deltas are large relative to the
sample sizes involved; I read this as "the dev-set result was not a fluke
that dissolves on unseen data," not as "the model performs better on
holdout" — with n=20/40, a few flipped claims in either direction would move
these numbers by several points.

The higher tool-error rate on holdout (0.15 vs 0.05) is fully explained by
five claims (`C-021`, `C-036`, `C-041`, `C-042`, `C-052`) that hit the
deliberately-missing February 2026 FX rate. The agent escalated correctly on
**all five**, citing S8 every time — the designed failure case worked exactly
as intended. It did retry the identical failing `convert_to_eur` call 3–4
times before conceding and escalating, which is correct but mildly wasteful;
a cheap improvement would be short-circuiting after one identical failure. A
sixth tool error (`C-049`) was the model passing a stray `result` keyword
argument to `get_handbook_section` — it self-corrected on the next call and
still reached the right decision, confirming the malformed-arguments path
required by Task 3 works without needing a crash or a retry-count limit.

## Cost/quality comparison and recommendation

**Recommend: the large model (`gemini/gemini-3.8-flash`), with a hard rule
that a `no_decision` outcome (step-limit hit, unrecovered tool error, or
repeated invalid submission) always routes to a human — never treat
"the agent didn't finish" as "the agent said approve."**

This is a hybrid by construction, not a separate configuration: on the dev
set, the large model produced zero wrong decisions among the 16/20 claims it
resolved. Its entire error budget was claims it declined to finish. That is
the failure mode you want in a finance tool — it fails by asking for help,
not by confidently paying out the wrong amount. The small model is roughly
5.4x cheaper per claim, but its errors are real wrong answers, and on this
sample it never once correctly caught a late-submission rejection, which is
exactly the kind of claim a real finance team would expect an automated
system to catch on the first pass.

The "easy claim" boundary this implies is mechanical and auditable: a claim
is easy if the agent reaches a valid `submit_decision` call within
`max_steps` (16) without an unrecovered tool error. Everything else — about
20% of dev volume for the large model — goes to a human. That 20% is not
noise to be tuned away before shipping; see Limitations.

At Nordlys's current backlog (roughly triple normal volume, three weeks
behind), even routing 20% to humans and auto-processing the rest at ~€0.08–
€0.11/claim is a large reduction in the volume of full manual review, at a
cost per claim that is trivial next to ~8 minutes of staff time.

## Cost projection at scale

Annual API cost if this were deployed, using the recommended configuration
(large model, `no_decision` routed to a human) and the currency correction
above applied properly (USD amounts × 0.86 → EUR, September 2026 rate).

**Real historical Gemini pricing** (USD per million tokens), rather than an
assumed decline curve:

| Date | Model | Input $/M | Output $/M |
|---|---|---|---|
| Feb 2025 | Gemini 2.0 Flash | $0.15 | $0.60 |
| Jun 2025 | Gemini 2.5 Flash | $0.30 | $2.50 |
| Sep 2026 (now) | Gemini 3.5 Flash-Lite (our "small") | $0.30 | $2.50 |
| Sep 2026 (now) | Gemini 3.8 Flash (our "large") | $0.75 | $3.75 |

Two things follow from this table that matter more than "does AI get
cheaper": from Feb to Jun 2025, **output-token price roughly quadrupled**
when "thinking" tokens became standard and started billing at the output
rate — the same phenomenon this project hit directly (§ Setup: both
candidate large-model IDs returned empty output until `max_tokens` was
raised, because the token budget was being consumed by invisible reasoning
before any visible answer). Then, for the 15 months from Jun 2025 to now,
**the price for that same tier did not move at all**. The trend for this
class of workload has been one step increase followed by a long flat period,
not a smooth curve — projecting a continued decline is not supported by the
data actually available, and projecting a continued flat line is the best-
evidenced default. A further step increase, if reasoning usage keeps
expanding, is at least as plausible as a decrease.

**Per-claim cost**, computed from this project's own measured token mix on
the holdout run (60,940 input / 6,072 output tokens/claim, large-model
config) rather than by rescaling the total cost, so that input- and
output-price movements (which have moved very differently) propagate
correctly:

| Scenario | $/claim | €/claim |
|---|---|---|
| Base — current pricing holds flat (best-supported by the last 15 months of actual data) | $0.0685 | €0.0589 |
| Ceiling — one more reasoning-driven repricing step, same magnitude as the one already observed (2.0→2.5) | $0.1368 | €0.1176 |

A "floor" scenario (pricing reverting to Feb-2025 levels) was considered and
dropped: nothing in the last 15 months of actual pricing history supports a
reversal, and the one repricing event we do have evidence for went the other
direction. Treating a price drop as a planning assumption would be optimism,
not measurement.

**Annual projection**, at a few illustrative volumes — Nordlys's actual
annual claim count is not stated anywhere in the case brief (only that
volume "roughly tripled" and the team is "three weeks behind"), so this is
parametrized rather than pinned to one guessed number:

| Scenario | 2,000 claims/yr | 10,000/yr | 50,000/yr |
|---|---|---|---|
| Base | €118 | €589 | €2,944 |
| Ceiling | €235 | €1,176 | €5,882 |

**What this does not include:** the human-review cost for the ~17.5–20% of
claims routed to a person. The LLM-API figures above already include the
wasted API spend on step-limited claims that never reach a decision (the
per-claim average is total cost over *all* claims, not just resolved ones),
but they say nothing about staff time. At the case's own figure of ~8
minutes/claim for a fully manual review, and using the escalation rate above
as an estimate of the reviewed fraction, that cost is straightforward to add
given a loaded hourly staff rate — deliberately left out here rather than
guessed. This projection also assumes claim complexity and the length of
agent trajectories stay similar to the 60-claim fixture; a heavier real-world
mix of line items per claim would raise both the token count per claim and
the step-limit rate.

## Failure analysis

**1. Step-limit non-completion, and it is not one failure mode.** Reading
individual trajectories showed two distinct patterns under the same metric.
Some are legitimate: claim `C-001` (small model, prompt v2) worked through
five line items one section at a time with no repeated calls and simply
needed more than 12 steps — raising `MAX_STEPS` 12→16 fixed this class.
Others are a different problem: claim `C-019` (large model) had gathered
every fact it needed by step 12 (all sections read, all currencies
converted) and then, instead of calling `submit_decision`, spent steps 13–16
searching the handbook for literal strings like `"cited_sections"` — as if
hunting for how to format the submission rather than what to decide. That
trajectory cost €0.14, about twice the median, for zero output. Raising the
step ceiling further would likely help the first pattern and do nothing for
the second.

**2. Retrieving a rule is not the same as applying it.** Claim `C-002`
(small model, prompt v1): the agent called `get_handbook_section("S10")`,
read the 90-day deadline rule, cited S10 in its final answer — and still
approved a claim submitted 126 days after the last expense. Claim `C-017`
(small model, prompt v2, later run): the agent asserted "submitted within 90
days" in its reasoning when the actual gap was 102 days, with no shown
arithmetic. Adding an explicit checklist instruction to compute exact day
counts improved this (reject recall 0.00→0.33 on the next small-model run)
but did not eliminate it, and it never recurred for the large model. This
looks like a genuine small-model capability gap around multi-digit date
arithmetic embedded in a paragraph, not a prompt-wording problem — the fix
that would actually close it is a `days_between` tool, which the fixed
five-tool budget for this challenge doesn't allow.

**3. Over-citation relative to the label, which is a labeling-convention
mismatch, not a hallucination.** Both models routinely cite more sections
than `labels_dev.json`'s `applied_rules` lists, because the ground truth only
records sections that *changed* the outcome, while the agent (correctly,
per its instructions) cites every section it relied on, including ones it
checked and found inapplicable (e.g., citing S9 after confirming the claim
is within budget). This is why citation recall (0.80–0.95) is reported
separately from exact-match (0.05–0.35) in this harness — exact-match alone
would misrepresent reasonable, non-fabricated citations as errors. No
fabricated (nonexistent) section id was ever submitted successfully in any
run, because `DecisionSubmission` rejects unknown section ids before the
episode can end.

## Limitations

- **20 dev / 40 holdout claims is not enough to certify a 100% conditional
  accuracy claim.** The large model's "100% correct when it decides" result
  on dev (16/16) is a genuinely strong signal, but n=16 is small; a couple of
  flipped claims would materially change it. Treat it as "the recommended
  direction," not a warranted SLA.
- **The fixture is cleaner than real submissions.** Every claim here has
  well-formed line items, consistent currencies, and a machine-generated
  justification paragraph. Real grantees misspell cities, attach receipts as
  photos of receipts, and write justifications that don't map neatly onto
  handbook categories. None of that stress is present here.
- **The label engine and the agent share no code, but they share an
  author's understanding of the policy.** The ground truth in
  `labels_dev.json` / `labels_holdout.json.locked` is generated from the same
  constants as the handbook text (`bootstrap/generate_data.py`), which means
  the labels cannot be wrong in the way a human adjudicator sometimes is —
  there are no genuinely ambiguous claims in this dataset, and real policy
  handbooks have those.
- **Run-to-run variance was not measured.** Both configurations were run
  once per prompt version at `temperature=0.0`. Gemini's tool-calling and
  reasoning-token behavior is not perfectly deterministic even at
  temperature 0; a repeat-run variance check (same config, three runs) was
  not done here for cost/time reasons and should be done before trusting
  small differences between configurations.
- **What I would need to see before recommending this unsupervised:** a
  repeat-run variance check as above; a larger holdout (hundreds, not tens,
  of claims) with real submission text; and instrumentation on the
  `no_decision` path in production, since routing 20% of volume to humans
  is only safe if that routing actually happens reliably and those claims
  are then triaged with the same or better attention than a fully manual
  process would give them.

## Methodology

Built the five retrieval/lookup tools and `submit_decision` as plain
functions over the JSON fixtures (`src/tools.py`), exposed as JSON Schema
tool definitions (`src/schemas.py`), with `submit_decision`'s payload as a
Pydantic model (`src/models.py`) that rejects invalid submissions and lets
the agent retry rather than crashing the run. The loop
(`src/agent.py`) is deliberately plain — no framework — so that the stubbed
loop test in `tests/test_agent_loop.py` can drive it with a scripted model
and assert on exact tool dispatch, logging, and step-ceiling behavior without
any network access.

Iteration followed the sequence the challenge recommends: write a first
prompt, run the 20 dev claims, read full trajectories for the actual
failures (not just the aggregate numbers), change one thing, re-run. That
process caught two real bugs that had nothing to do with prompt wording —
`search_handbook`'s excerpt was a naive first-220-characters slice that cut
off the one table a claim actually needed, and a crash in the LLM call was
being silently dropped from scoring instead of counted as a failure — before
it caught the one real prompt fix that mattered (the claim-level gating
checklist). Full history with what changed and why is in `EXPERIMENTS.md`.

Held the holdout set (`labels_holdout.json.locked`) unopened until the
configuration decision was made from dev-set evidence alone; `src.eval`
only reads it when invoked with `--final`.

**With another day**, I would: add a `days_between` helper *inside* the
agent's own reasoning scaffold (not a new tool, since the tool budget is
fixed) to see whether forcing the date-arithmetic step explicitly closes the
S10 gap; run the repeat-run variance check; and build the human-review queue
for `no_decision` claims, since that queue is where all of this system's
actual risk now lives.
