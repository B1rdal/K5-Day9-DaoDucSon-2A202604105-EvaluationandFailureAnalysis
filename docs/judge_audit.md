# Judge audit — M2

Calibration replayed on 2026-11-18 with Python 3.13.18. FAIL is the positive
class: the judge must find failures. Source CSV labels and verdicts are unchanged.

| Criterion | n | TP | FP | FN | TN | Cohen's kappa | Precision | Recall | Meets all floors? | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| tone_ok | 100 | 24 | 4 | 6 | 66 | 0.757 | 0.857 | 0.800 | Yes | Eligible for tone checks on this calibration set. |
| helpful | 100 | 9 | 0 | 21 | 70 | 0.375 | 1.000 | 0.300 | No | Reject as a blocking gate. |

All floors must pass: kappa >= 0.6, precision >= 0.8, recall >= 0.7.
Tone agreement is 0.90; chance agreement is
`0.30*0.28 + 0.70*0.72 = 0.588`, giving kappa `0.312/0.412`.
Helpfulness agreement is 0.79; chance agreement is 0.664, giving
`0.126/0.336 = 0.375`. Perfect precision only means its nine flagged failures
were genuine: it misses 21/30 failures (70%). Polite, fluent wording often hides
wrong money amounts. This judge must not authorize money movement or replace
ledger-based checks.

## Rogan–Gladen correction

`p_corrected = (p_observed + specificity - 1) / (sensitivity + specificity - 1)`,
clipped to [0, 1]. Sensitivity is recall with FAIL positive.

| Criterion | Observed failure rate | Sensitivity | Specificity | Corrected failure rate |
|---|---:|---:|---:|---:|
| tone_ok | 0.280 | 0.800 | 66/70 = 0.942857 | 0.300 |
| helpful | 0.090 | 0.300 | 1.000 | 0.300 |

Correction estimates aggregate prevalence; it does not repair individual
verdicts or make the helpfulness judge suitable for gating. Error rates here
come from the same labeled sample, so recovering the human 30% rate is an
algebraic check, not held-out validation. New traffic must have comparable judge
error rates. Invalid probabilities and sensitivity + specificity <= 1 are
rejected. Undefined kappa raises ValueError and fails calibration.

## Disagreement audit and rubric actions

This analyzes the supplied replies and annotation notes; it is not a new,
independent human-labeling round. Metrics above use the original CSV, including
the known H-081 label issue.

| Case | Judge | Human | Assessment | Rubric or dataset action |
|---|---|---|---|---|
| H-008 | PASS | FAIL | Human supported: “em”, “anh”, “nha”, “check” are overly familiar under the service register. | Require neutral “anh/chị”; include familiar particles as negative examples. |
| H-017 | PASS | FAIL | Human supported by the note about an older customer; “bạn ơi … rồi nha” is too familiar. Age is not inferable from the reply alone. | Supply recipient context or default to neutral address when age is unknown. |
| H-029 | PASS | FAIL | Human supported: “không cần nhắn thêm” shuts the customer down despite the polite prefix. | Judge the whole message; “Dạ/vui lòng” cannot override dismissive instructions. |
| H-042 | FAIL | PASS | Human supported on tone: a short courteous confirmation is acceptable without an apology. | Remove mandatory apology/length requirements; separate completeness from tone. |
| H-051 | FAIL | PASS | Human supported: the source note explicitly permits “refund”. | Add permitted service terms instead of rejecting every English word. |
| H-063 | PASS | FAIL | Human supported by the source note: “sẽ hoàn thêm” promises money beyond the system outcome. | Prohibit unsupported future refund promises; verify amounts and approvals with code. |
| H-070 | PASS | FAIL | Human supported: laughing emojis are inappropriate in a complaint. | Include inappropriate emoji use as a negative example even in polite text. |
| H-081 | FAIL | PASS | Judge supported by the supplied note identifying a mistaken human label. Missing original ticket prevents independent verification of that contextual claim. | Propose human FAIL, re-adjudicate against the ticket, and version a corrected dataset; preserve this published CSV. |
| H-088 | FAIL | PASS | Human supported: duplicated “Dạ” is a harmless typo. | Tolerate minor duplication that preserves meaning and respect. |
| H-094 | PASS | FAIL | Human supported under the source's Vietnamese writing standard: diacritics are missing. | Make language quality explicit and separate it from factual correctness. |
| HL-015 | PASS | FAIL | Human supported by the CSV: reply 55,000 VND, annotated ledger 40,000. | Require exact ledger comparison by code; politeness does not make wrong money helpful. |
| HL-016 | PASS | FAIL | Human supported by the CSV: a long apology surrounds 55,000 VND, annotated ledger 35,000. | Grade factual outcome before style; apologies cannot reverse a wrong-amount verdict. |
| HL-020 | PASS | FAIL | Human supported by the CSV: reply 90,000 VND, annotated ledger 120,000. | Include under-refund and over-refund examples and provide authoritative outcome context. |

Helpfulness ledger amounts above come from this calibration CSV's notes, not
Day 8 claims sharing an order ID. The original transactions were not retrieved.

## Decision and limitations

Use the tone judge within its calibrated scope. Reject helpfulness for gating
until its rubric/context improve and fresh labels pass recalibration. Amounts,
approval and ownership require deterministic code.

Tone still misses 6/30 failures and falsely flags 4/70 acceptable replies. These
100 examples per criterion are public replay, not fresh model calls or a truly
held-out set. Human labels can be wrong; changes require adjudication and dataset
versioning. Rubric actions above are proposals, not newly generated verdicts:
editing a rubric cannot change frozen CSV replay. Collect new independent labels
before claiming an improved judge.

## Reproduce from src/

```powershell
.\.venv\Scripts\python.exe -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10
# exit 0, PASS floors, observed 0.28 -> corrected 0.30
.\.venv\Scripts\python.exe -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 8
# exit 1, expected FAIL floors, observed 0.09 -> corrected 0.30
.\.venv\Scripts\python.exe -m pytest -q -o addopts= tests/test_lab9_stats.py tests/test_lab9_m2_edges.py -k "not paired_bootstrap"
```

Paired-bootstrap tests belong to M4, outside this M0–M2 scope.
