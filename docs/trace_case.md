# Trace case — C-002, authoritative delay versus ticket

This M1 case uses the original, unmodified swarm. Public observations and run
IDs are in [m1_traces.json](evidence/m1_traces.json). It is not an M4 scored
baseline: that report requires the M3 graders first.

| Field | Observation |
|---|---|
| Trial | `swarm C-002@55`, run ID `R-swarm-C-002-s55`. |
| Symptom | Lab 8 grader FAIL: `status resolved != denied`. Ledger commits 20,000 VND although the label requires 0. The original swarm emits no final reply event, so no customer-facing wording is inferred. |
| First wrong step | Event 3, `model_override`, payload `{"delay_days": 5}`. |
| Why first | Event 1 validly scopes the handoff to C-002. Event 2 reads the authoritative order with delay 2. The customer's ticket claims 5 days; event 3 substitutes that unverified number before compensation is computed. |
| Failure mode | FM-03, `ticket_trust`. The later nonzero quote and refund are consequences of the overridden fact. |
| Control | `fixed C-002@55`: event 3 is a quote of 0, no override, result denied and ledger 0. `swarm C-002@11` also passes with ledger 0, demonstrating seed dependence. |
| Regression test | `tests/test_lab9_m1_trace_case.py::test_authoritative_delay_boundary`: original Lab 8 grader rejects `swarm@55`, accepts `swarm@11` and `fixed@55`; explicit assertions check the first override and ledger. |
| Uncertainty | Trace exposes the substituted fact, not internal reasoning. MockLLM does not establish real-model error frequency. Host approval validity alone cannot prevent this eligibility error because C-002 has a valid 20,000 VND approval. |

Reproduce from `src/`:

```powershell
.\.venv\Scripts\python.exe -m lab9.trace_case --shape swarm --claim C-002 --seed 55
.\.venv\Scripts\python.exe -m lab9.trace_case --shape fixed --claim C-002 --seed 55
.\.venv\Scripts\python.exe -m pytest -q -o addopts= tests/test_lab9_m1_trace_case.py
```

The test intentionally demonstrates the known swarm failure and the passing
control; it does not modify Lab 8 to repair the agent.
