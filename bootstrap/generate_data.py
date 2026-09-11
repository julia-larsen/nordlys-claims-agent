"""Generate the fixture dataset for the reimbursement triage challenge.

Deterministic: same seed -> byte-identical output. The policy handbook and the
ground-truth labels are both derived from the constants below, so they cannot
drift apart.

Run once from the repo root:  python bootstrap/generate_data.py
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

SEED = 20260909
OUT = Path(__file__).resolve().parent.parent / "data"

# --- Policy constants. The handbook text is rendered from these. ---------

TIERS: dict[str, list[str]] = {
    "tier_a": ["Zurich", "London", "Copenhagen", "Oslo", "Stockholm", "Geneva"],
    "tier_b": ["Berlin", "Paris", "Amsterdam", "Vienna", "Dublin", "Munich"],
    "tier_c": ["Warsaw", "Lisbon", "Prague", "Athens", "Budapest", "Riga"],
}
PER_DIEM = {
    "tier_a": {"junior": 65, "senior": 80, "principal": 95},
    "tier_b": {"junior": 55, "senior": 68, "principal": 80},
    "tier_c": {"junior": 45, "senior": 55, "principal": 65},
}
LODGING_CAP = {"tier_a": 180, "tier_b": 140, "tier_c": 95}
FIELD_UPLIFT = 1.20
RECEIPT_THRESHOLD = 25.00
PREAPPROVAL_THRESHOLD = 800.00
LATE_SUBMISSION_DAYS = 90
RAIL_PREFERRED_KM = 600

NEVER_REIMBURSABLE = [
    "alcohol",
    "minibar",
    "traffic or parking fines",
    "travel class or room upgrades",
    "in-flight or in-hotel wifi",
]

CURRENCIES = ["DKK", "SEK", "CHF", "GBP", "PLN"]
BASE_RATES = {"DKK": 0.1341, "SEK": 0.0879, "CHF": 1.0512, "GBP": 1.1734, "PLN": 0.2331}
MONTHS = [
    "2025-09", "2025-10", "2025-11", "2025-12",
    "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06",
]
FX_GAP_MONTH = "2026-02"  # rate table deliberately unpublished for this month

CITY_TIER = {c: t for t, cities in TIERS.items() for c in cities}


@dataclass
class Line:
    line_id: str
    date: str
    category: str
    description: str
    amount: float
    currency: str
    receipt_attached: bool
    nights: int | None = None
    days: int | None = None
    distance_km: int | None = None

    def json(self) -> dict:
        d = {
            "line_id": self.line_id,
            "date": self.date,
            "category": self.category,
            "description": self.description,
            "amount": round(self.amount, 2),
            "currency": self.currency,
            "receipt_attached": self.receipt_attached,
        }
        for k in ("nights", "days", "distance_km"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        return d


@dataclass
class Claim:
    claim_id: str
    grantee_id: str
    budget_code: str
    destination_city: str
    submitted_on: str
    justification: str
    lines: list[Line] = field(default_factory=list)

    def json(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "grantee_id": self.grantee_id,
            "budget_code": self.budget_code,
            "destination_city": self.destination_city,
            "submitted_on": self.submitted_on,
            "justification": self.justification,
            "line_items": [l.json() for l in self.lines],
        }


def build_fx(rng: random.Random) -> dict[str, dict[str, float]]:
    table: dict[str, dict[str, float]] = {}
    for m in MONTHS:
        if m == FX_GAP_MONTH:
            continue
        table[m] = {
            ccy: round(base * (1 + rng.uniform(-0.02, 0.02)), 4)
            for ccy, base in BASE_RATES.items()
        }
        table[m]["EUR"] = 1.0
    return table


def to_eur(amount: float, ccy: str, day: str, fx: dict) -> float | None:
    if ccy == "EUR":
        return round(amount, 2)
    month = day[:7]
    if month not in fx or ccy not in fx[month]:
        return None
    return round(amount * fx[month][ccy], 2)


GRANTEE_NAMES = [
    ("G-001", "Marit Solberg", "senior", "Norway", "travel"),
    ("G-002", "Tomás Ferreira", "junior", "Portugal", "travel"),
    ("G-003", "Ines Kowalczyk", "principal", "Poland", "field"),
    ("G-004", "Bram de Vries", "senior", "Netherlands", "travel"),
    ("G-005", "Aoife Byrne", "junior", "Ireland", "field"),
    ("G-006", "Lukas Brenner", "principal", "Switzerland", "travel"),
    ("G-007", "Selin Aydın", "senior", "Germany", "field"),
    ("G-008", "Nikolaj Holm", "junior", "Denmark", "travel"),
    ("G-009", "Chiara Ferri", "senior", "Italy", "travel"),
    ("G-010", "Anna Lindqvist", "principal", "Sweden", "travel"),
    ("G-011", "Petros Manolis", "junior", "Greece", "field"),
    ("G-012", "Hana Novotná", "senior", "Czechia", "travel"),
]

BUDGET_CODES = [
    ("BUD-MOBILITY-01", "Researcher Mobility 2026", 41200.00),
    ("BUD-MOBILITY-02", "Researcher Mobility 2026 (reserve)", 480.00),
    ("BUD-FIELD-01", "Field Visits 2026", 33800.00),
    ("BUD-FIELD-02", "Field Visits 2026 (reserve)", 610.00),
    ("BUD-CONF-01", "Conference Attendance 2026", 25400.00),
    ("BUD-CONF-02", "Conference Attendance 2026 (reserve)", 350.00),
]

JUSTIFY_OPEN = [
    "Trip to {city} for the {purpose}.",
    "Travelled to {city}, {purpose}.",
    "{purpose} in {city}, as agreed with my supervisor.",
    "Claim covers the {purpose} in {city} last month.",
]
PURPOSES = [
    "annual methods workshop",
    "partner site visit",
    "steering committee meeting",
    "data collection round",
    "consortium kickoff",
    "training week",
    "stakeholder interviews",
]
VAGUE_TAILS = [
    " Receipts are attached where I still had them.",
    " Sorry this is late, it has been a busy quarter.",
    " Happy to provide more detail if needed.",
    " Let me know if anything is missing.",
    "",
]


def main() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)

    fx = build_fx(rng)

    grantees = [
        {
            "grantee_id": gid,
            "name": name,
            "grade": grade,
            "home_country": country,
            "grant_type": gtype,
        }
        for gid, name, grade, country, gtype in GRANTEE_NAMES
    ]
    by_id = {g["grantee_id"]: g for g in grantees}

    budgets = [
        {"budget_code": code, "label": label, "remaining_eur": rem}
        for code, label, rem in BUDGET_CODES
    ]
    budget_by_code = {b["budget_code"]: b for b in budgets}

    defects_pool = [
        "late_submission",
        "short_air_no_justification",
        "no_receipt_large",
        "alcohol_line",
        "minibar_line",
        "fine_line",
        "upgrade_line",
        "over_lodging_cap",
        "short_air_no_justification",
        "meals_on_per_diem_day",
        "late_submission",
        "missing_preapproval",
        "over_budget",
        "fx_gap",
        "clean",
        "clean",
        "clean",
    ]

    claims: list[Claim] = []
    labels: dict[str, dict] = {}

    # Guarantee coverage of every defect at least twice across the 60 claims.
    planned: list[list[str]] = []
    for d in defects_pool:
        planned.append([d] if d != "clean" else [])
    while len(planned) < 60:
        k = rng.choice([0, 1, 1, 2])
        planned.append(rng.sample([d for d in defects_pool if d != "clean"], k))
    rng.shuffle(planned)

    for i, defects in enumerate(planned[:60], start=1):
        cid = f"C-{i:03d}"
        g = rng.choice(grantees)
        tier_choice = rng.choice(["tier_a", "tier_b", "tier_c"])
        city = rng.choice(TIERS[tier_choice])
        tier = CITY_TIER[city]

        if g["grant_type"] == "field":
            code = "BUD-FIELD-01"
        else:
            code = rng.choice(["BUD-MOBILITY-01", "BUD-CONF-01"])

        month = FX_GAP_MONTH if "fx_gap" in defects else rng.choice(
            [m for m in MONTHS if m != FX_GAP_MONTH]
        )
        start = date.fromisoformat(f"{month}-01") + timedelta(days=rng.randint(2, 20))
        nights = rng.randint(1, 4)
        days = nights + 1

        ccy = rng.choice(CURRENCIES) if ("fx_gap" in defects or rng.random() < 0.3) else "EUR"

        cap_pd = PER_DIEM[tier][g["grade"]]
        cap_lodge = LODGING_CAP[tier]
        if g["grant_type"] == "field":
            cap_pd = round(cap_pd * FIELD_UPLIFT, 2)

        rate = fx.get(month, {}).get(ccy, BASE_RATES.get(ccy, 1.0))
        lines: list[Line] = []
        n = 0

        def add(cat: str, desc: str, eur_amount: float, **kw) -> Line:
            nonlocal n
            n += 1
            amt = eur_amount if ccy == "EUR" else eur_amount / rate
            ln = Line(
                line_id=f"{cid}-L{n}",
                date=(start + timedelta(days=kw.pop("offset", 0))).isoformat(),
                category=cat,
                description=desc,
                amount=round(amt, 2),
                currency=ccy,
                receipt_attached=kw.pop("receipt", True),
                **kw,
            )
            lines.append(ln)
            return ln

        nightly = cap_lodge * rng.uniform(0.7, 0.95)
        if "over_lodging_cap" in defects:
            nightly = cap_lodge * rng.uniform(1.15, 1.5)
        add("lodging", f"Hotel in {city}, {nights} nights", nightly * nights, nights=nights)

        daily = cap_pd * rng.uniform(0.85, 1.0)
        add("per_diem", f"Subsistence, {days} days", daily * days, days=days, offset=0)

        dist = rng.choice([220, 340, 480, 560, 720, 1100, 1650, 2100])
        if "short_air_no_justification" in defects:
            dist = rng.choice([220, 340, 480, 560])
            add("air", f"Return flight to {city}", rng.uniform(180, 340), distance_km=dist)
        elif dist < RAIL_PREFERRED_KM:
            add("rail", f"Return rail to {city}", rng.uniform(70, 190), distance_km=dist)
        else:
            add("air", f"Return flight to {city}", rng.uniform(160, 420), distance_km=dist)

        if rng.random() < 0.55:
            add(
                "taxi",
                "Airport transfer",
                rng.uniform(12, 44),
                receipt=not ("no_receipt_large" in defects),
                offset=1,
            )
        if rng.random() < 0.4:
            add("conference_fee", "Registration fee", rng.uniform(120, 380), offset=0)

        if "no_receipt_large" in defects:
            big = [
                l
                for l in lines
                if l.category != "per_diem"
                and (to_eur(l.amount, l.currency, l.date, fx) or 0.0) >= RECEIPT_THRESHOLD
            ]
            for l in lines:
                l.receipt_attached = True
            rng.choice(big or lines).receipt_attached = False
        if "alcohol_line" in defects:
            add("other", "Wine with the project dinner", rng.uniform(28, 64), offset=1)
        if "minibar_line" in defects:
            add("other", "Minibar charge on hotel bill", rng.uniform(14, 38), offset=1)
        if "fine_line" in defects:
            add("other", "Parking fine near the venue", rng.uniform(25, 70), offset=1)
        if "upgrade_line" in defects:
            add("other", "Seat upgrade to extra legroom", rng.uniform(35, 90), offset=0)
        if "meals_on_per_diem_day" in defects:
            add("meals", "Lunch with partner organisation", rng.uniform(18, 52), offset=1)

        total_claimed_eur = 0.0
        fx_failed = False
        for l in lines:
            e = to_eur(l.amount, l.currency, l.date, fx)
            if e is None:
                fx_failed = True
            else:
                total_claimed_eur += e

        pa_ref = f"PA-{month[:4]}-{rng.randint(100, 999)}"
        if "missing_preapproval" in defects:
            bump = max(0.0, PREAPPROVAL_THRESHOLD + 120 - total_claimed_eur)
            if bump > 0 and not fx_failed:
                lines[0].amount += round(bump / (1 if ccy == "EUR" else rate), 2)
                total_claimed_eur += bump
            has_pa = False
        else:
            has_pa = total_claimed_eur <= PREAPPROVAL_THRESHOLD or rng.random() < 0.9

        purpose = rng.choice(PURPOSES)
        text = rng.choice(JUSTIFY_OPEN).format(city=city, purpose=purpose)
        if has_pa and total_claimed_eur > PREAPPROVAL_THRESHOLD * 0.6:
            text += f" Pre-approval reference {pa_ref}."
        if "short_air_no_justification" not in defects and any(
            l.category == "air" and (l.distance_km or 0) < RAIL_PREFERRED_KM for l in lines
        ):
            text += " No direct rail connection was available on those dates."
        text += rng.choice(VAGUE_TAILS)

        last_expense = max(date.fromisoformat(l.date) for l in lines)
        lag = rng.randint(4, 40)
        if "late_submission" in defects:
            lag = rng.randint(LATE_SUBMISSION_DAYS + 5, LATE_SUBMISSION_DAYS + 60)
        submitted = last_expense + timedelta(days=lag)

        if "over_budget" in defects:
            code = (
                "BUD-FIELD-02"
                if g["grant_type"] == "field"
                else rng.choice(["BUD-CONF-02", "BUD-MOBILITY-02"])
            )

        claim = Claim(
            claim_id=cid,
            grantee_id=g["grantee_id"],
            budget_code=code,
            destination_city=city,
            submitted_on=submitted.isoformat(),
            justification=text,
            lines=lines,
        )
        claims.append(claim)

        # --- ground truth -------------------------------------------------
        applied: list[str] = []
        per_diem_days = {
            (date.fromisoformat(l.date) + timedelta(days=k)).isoformat()
            for l in lines
            if l.category == "per_diem"
            for k in range(l.days or 0)
        }

        if fx_failed:
            decision, reimbursable = "escalate", None
            applied = ["S8"]
        elif lag > LATE_SUBMISSION_DAYS:
            decision, reimbursable = "reject", 0.0
            applied = ["S10"]
        elif total_claimed_eur > budget_by_code[code]["remaining_eur"]:
            decision, reimbursable = "escalate", None
            applied = ["S9"]
        elif total_claimed_eur > PREAPPROVAL_THRESHOLD and not has_pa:
            decision, reimbursable = "escalate", None
            applied = ["S7"]
        else:
            total = 0.0
            for l in lines:
                eur = to_eur(l.amount, l.currency, l.date, fx) or 0.0
                allow = eur
                d = l.description.lower()
                if any(w in d for w in ("wine", "minibar", "fine", "upgrade", "wifi")):
                    allow, _ = 0.0, applied.append("S5")
                elif l.category == "meals" and l.date in per_diem_days:
                    allow, _ = 0.0, applied.append("S4")
                elif not l.receipt_attached and eur >= RECEIPT_THRESHOLD:
                    allow, _ = 0.0, applied.append("S6")
                elif l.category == "lodging":
                    per_night = eur / (l.nights or 1)
                    if per_night > cap_lodge:
                        allow, _ = round(cap_lodge * (l.nights or 1), 2), applied.append("S3")
                elif l.category == "per_diem":
                    per_day = eur / (l.days or 1)
                    if per_day > cap_pd:
                        allow, _ = round(cap_pd * (l.days or 1), 2), applied.append("S2")
                    if g["grant_type"] == "field":
                        applied.append("S11")
                elif l.category == "air" and (l.distance_km or 0) < RAIL_PREFERRED_KM:
                    if "no direct rail" not in text.lower():
                        allow, _ = 0.0, applied.append("S12")
                total += allow
            reimbursable = round(total, 2)
            decision = "approve" if reimbursable > 0 else "reject"

        labels[cid] = {
            "claim_id": cid,
            "decision": decision,
            "reimbursable_eur": reimbursable,
            "applied_rules": sorted(set(applied)),
        }

    dev = {k: v for k, v in labels.items() if int(k.split("-")[1]) <= 20}
    hold = {k: v for k, v in labels.items() if int(k.split("-")[1]) > 20}

    (OUT / "claims.json").write_text(
        json.dumps([c.json() for c in claims], indent=2, ensure_ascii=False)
    )
    (OUT / "grantees.json").write_text(json.dumps(grantees, indent=2, ensure_ascii=False))
    (OUT / "budgets.json").write_text(json.dumps(budgets, indent=2))
    (OUT / "fx_rates.json").write_text(json.dumps(fx, indent=2))
    (OUT / "labels_dev.json").write_text(json.dumps(dev, indent=2))
    (OUT / "labels_holdout.json.locked").write_text(json.dumps(hold, indent=2))
    (OUT / "policy_handbook.md").write_text(render_handbook())

    counts: dict[str, int] = {}
    for v in labels.values():
        counts[v["decision"]] = counts.get(v["decision"], 0) + 1
    print(f"claims: {len(claims)}  dev: {len(dev)}  holdout: {len(hold)}")
    print("decisions:", counts)


def render_handbook() -> str:
    tier_rows = "\n".join(
        f"| {t.replace('tier_', 'Tier ').upper()} | {', '.join(cities)} |"
        for t, cities in TIERS.items()
    )
    pd_rows = "\n".join(
        f"| {t.replace('tier_', 'Tier ').upper()} | €{PER_DIEM[t]['junior']} | "
        f"€{PER_DIEM[t]['senior']} | €{PER_DIEM[t]['principal']} |"
        for t in TIERS
    )
    lodge_rows = "\n".join(
        f"| {t.replace('tier_', 'Tier ').upper()} | €{LODGING_CAP[t]} |" for t in TIERS
    )
    never = "\n".join(f"- {x}" for x in NEVER_REIMBURSABLE)
    return f"""# Nordlys Foundation — Grantee Expense Handbook

Version 4.2. Applies to all expenses incurred on or after 1 September 2025.

## S1 — Scope and definitions

This handbook governs reimbursement of expenses incurred by grantees on
Foundation-funded activity. A *claim* covers a single trip or activity and may
contain several *line items*. Each line item is assessed on its own merits; a
defect in one line does not invalidate the remainder of the claim.

Destination cities are grouped into three cost tiers.

| Tier | Cities |
|---|---|
{tier_rows}

Cities not listed are treated as Tier C.

## S2 — Subsistence (per diem)

Subsistence is claimed as a flat daily rate, not against receipts. The maximum
daily rate depends on the destination tier and the grantee's grade.

| Tier | Junior | Senior | Principal |
|---|---|---|---|
{pd_rows}

Where a grantee claims more than the applicable maximum, the excess is not
reimbursable. The remainder of the line is paid at the maximum rate.

## S3 — Lodging

Lodging is reimbursed against receipts up to a maximum per night.

| Tier | Max per night |
|---|---|
{lodge_rows}

The cap applies per night, not to the invoice total. Where the nightly rate
exceeds the cap, reimburse the cap multiplied by the number of nights; the
excess is borne by the grantee.

## S4 — Meals

Meals are covered by the subsistence rate in S2. A meal receipt dated on a day
for which subsistence has been claimed is not separately reimbursable. Meal
receipts on days outside the subsistence period are assessed under S6.

## S5 — Categories that are never reimbursable

Regardless of receipts, approval, or budget availability, the Foundation does
not reimburse:

{never}

Where such an item appears as a line of its own, that line is reimbursed at
zero. Where it is embedded in a larger invoice, the grantee must resubmit an
itemised version.

## S6 — Receipts

A receipt is required for any single line item of €{RECEIPT_THRESHOLD:.0f} or more. Lines below
that threshold may be self-declared. A line at or above the threshold with no
receipt attached is reimbursed at zero. Subsistence claimed under S2 is exempt
from this section.

## S7 — Advance approval

A claim whose total exceeds €{PREAPPROVAL_THRESHOLD:.0f} requires a pre-approval reference issued before
travel, in the form `PA-YYYY-NNN`. The reference must appear in the claim.
A claim over the threshold with no reference is referred to the Grants Officer;
it is neither approved nor rejected by the finance team.

## S8 — Currency

Expenses in a currency other than the euro are converted using the Foundation's
published monthly rate for the month in which the expense was incurred, not the
month of submission. Where no rate has been published for that month, the claim
is referred to the Grants Officer.

## S9 — Budget availability

A claim whose total exceeds the remaining balance on its budget code is
referred to the Grants Officer, whatever its other merits. The finance team
does not partially disburse against an exhausted code.

## S10 — Submission deadline

A claim submitted more than {LATE_SUBMISSION_DAYS} days after the last expense date in the claim is
rejected in full.

## S11 — Field-visit grants

Grantees on a field-visit grant work in conditions where the standard
subsistence rates in S2 are known to be insufficient. For these grantees, and
for subsistence only, the applicable maximum daily rate in S2 is increased by
{int((FIELD_UPLIFT - 1) * 100)}%. All other sections apply unchanged, including the lodging caps in S3.

## S12 — Mode of travel

For journeys under {RAIL_PREFERRED_KM} km one way, rail is the default mode. Air travel on such a
route is reimbursable only where the claim states that rail was unavailable or
unsuitable. Without such a statement, the air line is reimbursed at zero. For
journeys of {RAIL_PREFERRED_KM} km or more, either mode is acceptable without justification.

## S13 — Outcomes

Every claim resolves to exactly one of:

- **approve** — at least part of the claim is reimbursable. Record the
  reimbursable total in euro, which may be less than the amount claimed.
- **reject** — nothing in the claim is reimbursable.
- **escalate** — the finance team is not authorised to decide. Sections S7, S8
  and S9 produce this outcome. No amount is recorded.

Where more than one section applies, escalation under S8 takes precedence,
then S10, then S9, then S7. Only if none of these apply are the line-level
sections assessed.
"""


if __name__ == "__main__":
    main()
