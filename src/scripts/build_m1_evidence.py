"""Replay public M1 examples without changing Lab 8 or the supplied variants.

Run from src/: python -m scripts.build_m1_evidence
These are trace observations, not a scored M4 baseline or an instructor anchor key.
"""

import json
from pathlib import Path

from lab8.console import utf8_stdio
from lab8.shapes import SHAPES
from lab9.evalset import sha12
from lab9.trace_case import investigate
from lab9.variant_agent import make_shape


EXAMPLES = [
    ("FM-01", "leaky_trace", "C-001"),
    ("FM-02", "ignore_denied", "C-007"),
    ("FM-03", "ticket_trust", "C-002"),
    ("FM-04", "sum_parts", "C-014"),
    ("FM-05", "pre_deducted", "C-014"),
    ("FM-06", "stale_clause", "C-006"),
    ("FM-07", "sibling_refund", "C-001"),
    ("FM-08", "misreport", "C-008"),
]


def observe(shape, claim_id, seed, failure_mode=None):
    trial = investigate(shape, claim_id, seed)["trial"]
    return {
        "shape": shape, "claim_id": claim_id, "seed": seed,
        "failure_mode": failure_mode, "run_id": trial["result"]["run_id"],
        "result": trial["result"], "snapshot": trial["snapshot"],
        "unexpected_rows": trial["unexpected_rows"],
        "lab8_pass": trial["lab8_pass"], "lab8_reason": trial["lab8_reason"],
        "events": [{"step": n, **e} for n, e in enumerate(trial["events"], 1)],
    }


def main():
    utf8_stdio()
    rows = []
    for fm, bug, claim_id in EXAMPLES:
        shape = f"m1_{bug}"
        SHAPES[shape] = make_shape(shape, {"no_override", bug})
        rows.append(observe(shape, claim_id, 11, fm))
    claims = [json.loads(line) for line in Path("data/public_claims.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    for claim in claims:
        row = observe("fixed", claim["claim_id"], 11)
        if not row["lab8_pass"]:
            raise RuntimeError(f"fixed control failed: {claim['claim_id']}: {row['lab8_reason']}")
        rows.append(row)
    for seed in (11, 55):
        rows.append(observe("swarm", "C-002", seed, "FM-03"))
    out = Path("../docs/evidence/m1_traces.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "generator": "python -m scripts.build_m1_evidence",
        "claims_sha12": sha12(Path("data/public_claims.jsonl")),
        "world_sha12": sha12(Path("data/public_world_state.json")),
        "observations": rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(rows)} public trace observations")
    for row in rows:
        print(row["shape"], row["claim_id"], row["seed"],
              row["lab8_pass"], row["lab8_reason"],
              "ledger=", row["snapshot"]["refund_vnd"], "unexpected=", row["unexpected_rows"])
        for event in row["events"]:
            print(event["step"], event["kind"], json.dumps(event["payload"], ensure_ascii=False))


if __name__ == "__main__":
    main()
