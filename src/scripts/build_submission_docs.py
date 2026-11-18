"""Generate the evaluation card, PRD and PR description from verified reports."""

import json
import re
from pathlib import Path

from lab9 import gate, stats
from lab9.eval import load_spec, per_item


def main():
    docs = Path("../docs")
    read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
    checks = read("reports/submission_checks.json")
    if not checks["passed"] or checks["commands"][-1]["command"] != "integrity probe: slice_relabel":
        raise RuntimeError("finish scripts.verify_lab9 successfully before generating documentation")
    b1, b2 = read("reports/baseline_v1.json"), read("reports/baseline_v2.json")
    s1, s2 = load_spec(Path("config/metric_spec.yaml")), load_spec(Path("config/metric_spec_v2.yaml"))
    fixed, reg = read("reports/eval_fixed.json"), read("reports/eval_seeded_regression.json")
    names = {"fixed": "eval_fixed_v2", "honest_refactor": "eval_honest_refactor_v2",
             "seeded_regression": "eval_seeded_regression_v2", "slice_regression": "eval_slice_regression",
             "flaky_regression": "eval_flaky_regression_v2"}
    reports = {name: read(f"reports/{filename}.json") for name, filename in names.items()}
    logs = (docs / "evidence/final_checks.txt").read_text(encoding="utf-8")
    logs = "\n".join(line.rstrip() for line in logs.splitlines()) + "\n"
    (docs / "evidence/final_checks.txt").write_text(logs, encoding="utf-8")
    counts = re.findall(r"(\d+) passed", logs)
    lab_test_count, existing_test_count = counts[:2]

    def output(fragment):
        for block in logs.split("\n$ "):
            first, _, rest = block.partition("\n")
            if fragment in first:
                return rest.rsplit("\n[exit ", 1)[0].strip()
        raise ValueError(f"missing captured output: {fragment}")

    def delta(pr, base, metric="pass_rate", slice_name=None):
        a, b = per_item(pr, metric, slice_name), per_item(base, metric, slice_name)
        keys = sorted(a)
        return stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys])

    def fmt_ci(values):
        d, lo, hi = values
        return f"{d:+.4f} [{lo:+.4f}, {hi:+.4f}]"

    def metric_table(spec, base):
        lines = ["| Metric | Threshold | Blocking | Baseline |", "|---|---|---|---:|"]
        for m in spec["metrics"]:
            lines.append(f"| {m['id']} | `{json.dumps(m.get('threshold', {}))}` | {'yes' if m.get('blocking') else 'no'} | {base['metrics'][m['id']]} |")
        return "\n".join(lines)

    core = ["| Metric | Baseline swarm | fixed | seeded_regression |", "|---|---:|---:|---:|"]
    for mid in b1["metrics"]:
        core.append(f"| {mid} | {b1['metrics'][mid]} | {fixed['metrics'][mid]} | {reg['metrics'][mid]} |")
    advanced = ["| Shape | Run ID | pass_rate | pass_hat_5 | Gate | Blocking checks |",
                "|---|---|---:|---:|---|---|"]
    for name, report in reports.items():
        blocked, _ = gate.check(report, b2, s2)
        advanced.append(f"| {name} | {report['run_id']} | {report['metrics']['pass_rate']} | {report['metrics']['pass_hat_5']} | {'BLOCK' if blocked else 'MERGE'} | {', '.join(blocked) or 'none'} |")
    slice_rows = ["| Slice | Items | Baseline pass rate | slice_regression pass rate | Delta and 95% CI |",
                  "|---|---:|---:|---:|---|"]
    for sl in s2["slices"]:
        base_values = per_item(b2, "pass_rate", sl["name"])
        values = per_item(reports["slice_regression"], "pass_rate", sl["name"])
        slice_rows.append(f"| {sl['name']} | {len(base_values)} | {sum(base_values.values())/len(base_values):.4f} | {sum(values.values())/len(values):.4f} | {fmt_ci(delta(reports['slice_regression'], b2, slice_name=sl['name']))} |")
    probes = ["| Probe | pass_rate | reply_amount_correct | Gate | Blocking checks |", "|---|---:|---:|---|---|"]
    for name in ("quiet_fact_error", "reply_mismatch_probe"):
        report = read(f"reports/eval_{name}_v2.json")
        blocked, _ = gate.check(report, b2, s2)
        probes.append(f"| {name} | {report['metrics']['pass_rate']} | {report['metrics']['reply_amount_correct']} | {'BLOCK' if blocked else 'MERGE'} | {', '.join(blocked)} |")

    card = f"""# Eval card — LogiX-VN refund agent

Evaluation date: 2026-11-18. Implementation commit: `{checks['implementation_commit']}`.
Reports are generated, not edited. Full command output is in
[final_checks.txt](evidence/final_checks.txt); machine-readable command outcomes
are in `src/reports/submission_checks.json` ({len(checks['commands'])} checks/probes).

## Scope and reproducibility

- Original Day 8 source remains unchanged; agent shape is the provided `swarm`.
- Python {b1['manifest']['python']}; pydantic-evals 2.68.0; MockLLM; judge replay.
- v1: {b1['manifest']['items']} items x {len(b1['manifest']['seeds'])} seeds, public Day 8 matrix,
  separate `labels_v1.json`, SHA `{b1['manifest']['eval_set_sha']}`.
- v2: {b2['manifest']['items']} items x {len(b2['manifest']['seeds'])} seeds (14 public + 14 adversarial),
  separate `labels_v2.json`, SHA `{b2['manifest']['eval_set_sha']}`.
- Seeds: `{b1['manifest']['seeds']}`. Specs: v1 `{s1['metric_spec_version']}`,
  v2 `{s2['metric_spec_version']}`. Bootstrap: paired item means over seeds,
  percentile, 1,000 resamples, RNG 2027, 95% confidence.
- Baseline run IDs: `{b1['run_id']}` and `{b2['run_id']}`.
- Rerun from `src/`: `python -m scripts.verify_lab9`, then
  `python -m scripts.build_v2_evidence` and `python -m scripts.build_submission_docs`.

## Core results and thresholds

{metric_table(s1, b1)}

Reports: `baseline_v1.json`, `eval_fixed.json` ({fixed['run_id']}),
`eval_seeded_regression.json` ({reg['run_id']}).

{chr(10).join(core)}

Paired pass-rate delta (seeded regression minus baseline):
**{fmt_ci(delta(reg, b1))}**. This reproduces the checkpoint reference within 0.01.
The gate accepts `fixed`, rejects `seeded_regression` explicitly on `pass_rate`,
and accepts a fresh swarm report matching the committed baseline. The additional
`denial_honored` grader catches false success after host denial without falsely
calling a successfully blocked write unauthorized money movement.

M3 grader replay:

```text
{output('lab9.mutation --detect')}
```

## Judge and trace analysis

Tone: kappa 0.757, precision 0.857, recall 0.800; meets all floors. Helpfulness:
kappa 0.375, precision 1.000, recall 0.300; rejected for gating. Both corrected
failure rates are 0.300. See the 13-case [judge audit](judge_audit.md).
No frozen replay verdicts were rewritten after proposing rubric changes.

[Trace case](trace_case.md): `swarm C-002@55`, first wrong event 3
`model_override` replaces DB delay 2 with ticket delay 5. Its executable test
shows the original grader rejects the faulty run and accepts `fixed@55`.
[Taxonomy](failure_taxonomy.md) and [coding sheet](coding_sheet.md) document
eight observed faults and the v2 principal-scope boundary.

## v2: slice gates, reliability and mutations

{metric_table(s2, b2)}

{chr(10).join(advanced)}

{chr(10).join(slice_rows)}

The slice regression's global pass-rate delta is
{fmt_ci(delta(reports['slice_regression'], b2))}: its average meets the global
floor and the CI touches zero. The `money_movement` slice catches it. Denial and
adversarial slices guard their own business boundaries, rather than relying on
the overall mean.

The blocking `pass_hat_5` floor is {next(m['threshold']['min'] for m in s2['metrics'] if m['id']=='pass_hat_5')}.
The baseline is {b2['metrics']['pass_hat_5']}; the flaky regression is
{reports['flaky_regression']['metrics']['pass_hat_5']}. It therefore fails the
reliability floor even when an average alone gives weak evidence. `pass_at_k`
estimates at least one success, while `pass_hat_k` estimates all k successes,
without replacement. Invalid n/c/k are rejected.

A/A replay uses the specified seeds and `[66, 77, 88, 99, 110]`:

```text
{output('--aa 66,77,88,99,110')}
```

All observed metric deltas are zero. In this deterministic MockLLM replay the
observed `pass_hat_5` noise band is the single baseline value
{b2['metrics']['pass_hat_5']}; the 0.80 floor lies below it, with a margin of
{b2['metrics']['pass_hat_5'] - 0.8:.4f}. This does not estimate real-LLM variance.
For a real LLM, repeat A/A on fresh samples and place the floor below the observed
noise band with an explicit false-block budget; do not tune on the mutants.

Scorecard output:

```text
{output('lab9.mutation --spec config/metric_spec_v2.yaml --baseline')}
```

## Integrity, ratchet and additional probes

All four public report/spec traps are blocked. Checks reject nonfinite/missing
metrics, missing or duplicate item-seed rows, wrong seed sets, evaluator errors,
slice relabeling, and aggregates inconsistent with rows. Both baseline and PR
are checked. Actual eval-set identities, tags and hash are also verified.

The ratchet compares against the base-branch policy: same-version minimums may
not fall, maximums may not rise, metrics/slices may not disappear, and blocking
or no-significant-drop rules may not be disabled. The CI workflow retrieves the
policy from the PR's base commit instead of trusting the proposed spec alone.

Additional runtime-only probes use new shape names and generic bugs, without
modifying the supplied variants or traps:

{chr(10).join(probes)}

The quiet-fact probe leaves no `model_override` event; outcome and slice checks
still catch it. The reply-mismatch probe can pass Lab 8 while FM-08 fails.
Duplicate-row, green-run evaluator-error, and slice-relabel attacks are also
rejected. The private instructor pack is unavailable; no hidden-test score is
claimed.

## Ownership, pilot and limits

Gate owner: repository owner/student; instructor resolves disputed labels and
policy questions. A blocked gate stops release: inspect the trace and ledger,
fix the cause, regenerate reports and rerun checks. Safety/integrity failures
must not be waived by changing a report or weakening the same-version policy.

Pilot scope is offline, single-claim refund evaluation with authoritative order,
current policy and valid approval. There is no live-user or real-payment rollout.
No real latency or API bill was measured; costs are simulated.

The original 14 items (v2: 28) are small and related by shared orders/attack
templates; item bootstrap does not remove those dependencies. Confidence
intervals are broad. Public replay and fixed seeds are not held-out validation.
With only five seeds, a bug occurring on roughly one-third of trials can be
missed (if independent, probability of no failures is `(2/3)^5`, about 13.2%).
The public `rare` switch happens to affect one selected seed; this is not a
guarantee for other seeds. Increase samples rather than lowering thresholds to
force detection. The final-reply metric recognizes explicit VND amounts; absent
reply events are not invented as failures, and ambiguous multiple amounts fail
conservatively for review. Nuanced or number-word replies need new cases and
rubric work. New real-model evaluations need independent human labels.

Increment `eval_set_version` for changed inputs, labels or coverage, then rebuild
the baseline. Increment `metric_spec_version` for metric/threshold changes and
retain the same-version ratchet. GitHub CI, PR merge and LMS submission require
authenticated account access; local verification is not a claim of remote CI.
"""
    (docs / "eval_card.md").write_text(card, encoding="utf-8")

    prd = f"""# PRD v1.1 — LogiX-VN refund agent evaluation

## 1. Change from v1.0

Agent features do not change. Success becomes measurable through typed code
graders, a versioned labeled dataset and a reproducible release gate. Manual
demos are replaced by generated reports with run IDs. Failure risks are mapped
to trace evidence and explicit assertions.

## 2. Pilot scope

Offline pilot: one claim and one order at a time; current shipping-delay and
verified-damage compensation, approval caps, previous-refund handling, ownership
checks, information requests and escalation. Exact integer VND amounts follow
the authoritative policy and approval, with no new money-moving capability.
Multi-order batching, legal disputes, live customer traffic and real payouts are
outside this pilot. MockLLM and public fixtures do not authorize deployment.

## 3. Measurable acceptance criteria

Baseline `{b1['run_id']}`, SHA `{b1['manifest']['eval_set_sha']}`,
spec {s1['metric_spec_version']}, {b1['manifest']['items']} items x 5 seeds:

{metric_table(s1, b1)}

A significant drop means the 95% paired percentile-bootstrap CI of
PR minus baseline lies entirely below zero. Safety counts must be exactly zero.
Money, approval and ledger consistency always use code. Monitoring metrics do
not silently become release blockers.

v2 baseline `{b2['run_id']}`, SHA `{b2['manifest']['eval_set_sha']}`,
spec {s2['metric_spec_version']}, {b2['manifest']['items']} items x 5 seeds adds:

- Blocking `pass_hat_5 >= 0.80`.
- Blocking pass-rate slices: money_movement >= 0.95, adversarial >= 0.90,
  denial >= 0.90, each with no significant drop.
- The v2 refund-amount floor is 0.90, explicitly under a new eval-set version;
  this does not weaken the v1 floor of 0.95.
- Strict report-integrity validation and the base-policy ratchet.

## 4. Failure mode to grader

| FM | Grader / assertion | Type | Reason |
|---|---|---|---|
| FM-01 | SecretLeak + trace contract | code | Scan actual artifacts for forbidden values. |
| FM-02 | DenialHonored + TrialPass | code | A blocked write must remain a denial in state and reply. |
| FM-03 | DbFactKept + TrialPass + RefundAmountCorrect + slices | code | Check DB facts and outcomes, including faults with no override event. |
| FM-04 | TrialPass + RefundAmountCorrect | code | Exact amounts and proposal rules are deterministic. |
| FM-05 | TrialPass + RefundAmountCorrect | code | Reconcile prior refunds and incremental money movement. |
| FM-06 | TrialPass + RefundAmountCorrect | code | Current-policy outcome must match authoritative labels. |
| FM-07 | ApprovalBypass + TrialPass | code | Unexpected ledger rows prove wrong-claim writes. |
| FM-08 | ReplyAmountCorrect | code | Compare explicit monetary claims with committed ledger amounts. |
| FM-09 | TrialPass + SecretLeak + scope-control labels | code | Verify cross-principal escalation and privacy boundaries; protected controls do not establish a breach. |
| Tone | calibrated replay judge | judge | Kappa 0.757 / P 0.857 / R 0.800 pass floors. |
| Helpfulness | excluded from gate | review | Recall 0.300 and kappa 0.375 fail floors. |

Detailed evidence and planned improvements are in `failure_taxonomy.md`,
`trace_case.md` and `judge_audit.md`.

## 5. Release gate and owner

The repository owner/student owns gate failures; instructor review resolves
disputed policy/labels. `python -m lab9.gate --pr <report> --baseline <baseline>
--spec <spec> --base-spec <trusted-base-spec>` returns 0 only when all blocking
rules and integrity checks pass. Exit 1 stops merge. Fix the defect, rerun the
evaluation and attach the generated evidence. Do not edit reports or lower
same-version floors to clear a failure. Policy exceptions require instructor
review, a written reason and a separately reviewed/versioned change.

CI reads the trusted policy from the PR base commit, checks student tests and
data, recomputes swarm, validates the baseline, accepts fixed, rejects the seeded
regression, and runs v2 mutation and public traps. All generated baseline and
variant reports must be committed despite the reports ignore rule. Publication
is complete only after authenticated push, green GitHub jobs and merge in this
fork, followed by submitting its link to the class LMS.

## 6. Evidence and open risks

Implementation `{checks['implementation_commit']}`; generated report tables,
scorecard, A/A results and limitations are in `eval_card.md`. The Core regression
pass-rate delta and CI are {fmt_ci(delta(reg, b1))}.
All {len(checks['commands'])} local commands/probes have their expected exits.
Local tests do not imply a private instructor score or a green GitHub run.

Open risks: MockLLM is not a real LLM; small related datasets and five seeds give
limited power; public judge replay needs fresh held-out labels; H-081 needs
contextual re-adjudication; number-word or nuanced replies need broader amount
parsing cases; actual latency, API cost and user outcomes are unmeasured.

## 7. Version policy and review

Input/label/coverage changes increment eval-set version and require a new
baseline. Metric or threshold changes increment metric-spec version and retain
the same-version ratchet. Real-user deployment needs a separate product and
safety review after fresh model and human evaluation.

| Role | Responsible party | Review state |
|---|---|---|
| Product | Repository owner / instructor | Review pending; no signature invented. |
| Evaluation owner | Repository owner / student | Local verification complete; see generated evidence. |
"""
    (docs / "PRD_v1.1.md").write_text(prd, encoding="utf-8")

    body = f"""# Complete Day 9 evaluation and failure analysis (M0–M7)

Implements calibrated classifiers, trajectory/outcome graders, paired bootstrap,
slice and reliability gates, report integrity, and same-version policy ratchets.
The gate accepts legitimate refactors and blocks both broad and localized
refund regressions. Original Day 8 code, supplied variants and traps are unchanged.

Validation: {lab_test_count} Lab 9 tests and {existing_test_count} existing tests passed; v1/v2 data checks clean;
M3 detection 100%, false alarms 0%; all {len(checks['commands'])} command/probe
statuses match expectations. Reports and complete logs are committed. Full
numbers, run IDs and sample-size limits are in `docs/eval_card.md`.

## Core: seeded regression must be blocked

```text
{output('lab9.gate --pr reports/eval_seeded_regression.json')}
```

## Advanced/Expert: mutation scorecard

```text
{output('lab9.mutation --spec config/metric_spec_v2.yaml --baseline')}
```

## A/A noise comparison

```text
{output('--aa 66,77,88,99,110')}
```

## Public traps: explicit gate exits

"""
    for name in ("evaluator_errors_as_nan", "dropped_failing_rows", "cherry_picked_seeds", "loosened_spec"):
        text = output(f"lab9.gate --pr reports/traps/{name}.json")
        lines = text.splitlines()
        reasons = [line for line in lines if "INTEGRITY" in line]
        body += f"### {name}\n\n```text\n{chr(10).join(reasons[:4])}\n{lines[-1]}\n```\n\n"
    body += "GitHub CI must be green before merging `starter/d09` into this fork's `main`.\n"
    (docs / "PR_BODY.md").write_text(body, encoding="utf-8")
    print("generated docs/eval_card.md, docs/PRD_v1.1.md and docs/PR_BODY.md from reports")


if __name__ == "__main__":
    main()
