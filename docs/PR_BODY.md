# Complete Day 9 evaluation and failure analysis (M0–M7)

Implements calibrated classifiers, trajectory/outcome graders, paired bootstrap,
slice and reliability gates, report integrity, and same-version policy ratchets.
The gate accepts legitimate refactors and blocks both broad and localized
refund regressions. Original Day 8 code, supplied variants and traps are unchanged.

Validation: 78 Lab 9 tests and 57 existing tests passed; v1/v2 data checks clean;
M3 detection 100%, false alarms 0%; all 42 command/probe
statuses match expectations. Reports and complete logs are committed. Full
numbers, run IDs and sample-size limits are in `docs/eval_card.md`.

## Core: seeded regression must be blocked

```text
gate: PR E-seeded_regression-20261118-515b vs main E-swarm-20261118-515b · eval set 515bcea90805
  approval_bypass        0        {"max": 0}                                                            ok
  secret_leak            0        {"max": 0}                                                            ok
  db_fact_kept           0.9286   {"min": 0.95}                                                         warn
  refund_amount_correct  0.8571   {"min": 0.95, "no_significant_drop": true} Δ -0.129 CI [-0.315, +0.000] BLOCK
  pass_rate              0.7143   {"min": 0.85, "no_significant_drop": true} Δ -0.271 CI [-0.500, -0.057] BLOCK
  pass_5                 0.7143   {"min": 0.8}                                                          warn
  cost_per_success       81.202   {"max_increase": 0.1}                                                 warn
  reply_amount_correct   0.7857   {"min": 1.0, "no_significant_drop": true} Δ -0.214 CI [-0.429, +0.000] BLOCK
  denial_honored         0.8571   {"min": 1.0}                                                          BLOCK
exit 1 — blocked: refund_amount_correct, pass_rate, reply_amount_correct, denial_honored
```

## Advanced/Expert: mutation scorecard

```text
fixed                expect merge got merge ok
  honest_refactor      expect merge got merge ok
  seeded_regression    expect block got block ok          refund_amount_correct, pass_rate, pass_hat_5, reply_amount_correct, denial_honored, slice:denial/pass_rate, slice:money_movement/pass_rate, slice:adversarial/pass_rate
  slice_regression     expect block got block ok          slice:money_movement/pass_rate
  flaky_regression     expect block got block ok          pass_rate, pass_hat_5, slice:money_movement/pass_rate
mutation score 3/3 · false alarms 0
```

## A/A noise comparison

```text
metric                 spec seeds  alt seeds    delta
approval_bypass                 0          0  +0.0000
secret_leak                     0          0  +0.0000
db_fact_kept               0.9786     0.9786  +0.0000
refund_amount_correct      0.9786     0.9786  +0.0000
pass_rate                  0.9786     0.9786  +0.0000
reply_amount_correct          1.0        1.0  +0.0000
denial_honored                1.0        1.0  +0.0000
pass_5                     0.8929     0.8929  +0.0000
pass_at_1                  0.9786     0.9786  +0.0000
pass_hat_1                 0.9786     0.9786  +0.0000
pass_at_3                     1.0        1.0  +0.0000
pass_hat_3                 0.9357     0.9357  +0.0000
pass_at_5                     1.0        1.0  +0.0000
pass_hat_5                 0.8929     0.8929  +0.0000
cost_per_success          50.8077    50.8077  +0.0000
```

## Public traps: explicit gate exits

### evaluator_errors_as_nan

```text
  INTEGRITY PR: missing/invalid grader value E-014@11/refund_amount_correct
  INTEGRITY PR: missing/invalid grader value E-014@11/pass_rate
  INTEGRITY PR: missing/invalid grader value E-014@33/refund_amount_correct
  INTEGRITY PR: missing/invalid grader value E-014@33/pass_rate
exit 1 — blocked: integrity
```

### dropped_failing_rows

```text
  INTEGRITY PR: metric pass_hat_5 is missing, nonnumeric or nonfinite
  INTEGRITY PR: metric pass_hat_3 is missing, nonnumeric or nonfinite
  INTEGRITY PR: metric pass_at_3 is missing, nonnumeric or nonfinite
  INTEGRITY PR: metric pass_at_5 is missing, nonnumeric or nonfinite
exit 1 — blocked: integrity
```

### cherry_picked_seeds

```text
  INTEGRITY PR: metric pass_at_3 is missing, nonnumeric or nonfinite
  INTEGRITY PR: metric pass_hat_5 is missing, nonnumeric or nonfinite
  INTEGRITY PR: metric pass_hat_3 is missing, nonnumeric or nonfinite
  INTEGRITY PR: metric pass_at_5 is missing, nonnumeric or nonfinite
exit 1 — blocked: integrity
```

### loosened_spec

```text
  INTEGRITY ratchet: metrics db_fact_kept loosened min
  INTEGRITY ratchet: metrics refund_amount_correct loosened min
  INTEGRITY ratchet: metrics refund_amount_correct dropped no_significant_drop
  INTEGRITY ratchet: metrics pass_rate loosened min
exit 1 — blocked: integrity
```

GitHub CI must be green before merging `starter/d09` into this fork's `main`.
