"""Semantic checks against incomplete evidence, altered policies and rare faults."""

import copy
import itertools

import pytest

from lab9 import gate, stats
from lab9.graders import DenialHonored, ReplyAmountCorrect
from tests.test_lab9_graders import ctx, trial

pytestmark = pytest.mark.student


@pytest.fixture
def reports():
    spec = {"eval_set_version": "v2", "metrics": [
        {"id": "pass_rate", "kind": "capability", "blocking": True,
         "threshold": {"min": 0.8, "no_significant_drop": True}},
    ], "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.9,
                    "blocking": True, "no_significant_drop": True}]}
    report = {"manifest": {"eval_set_sha": "test", "items": 2, "seeds": [11, 22]},
              "rows": [{"item_id": item, "seed": seed, "pass_rate": True, "slices": ["money_movement"]}
                       for item in ("E-001", "E-002") for seed in (11, 22)],
              "metrics": {"pass_rate": 1.0}, "evaluator_failures": []}
    return report, spec


def test_clean_baseline_compared_with_itself_merges(reports):
    base, spec = reports
    assert gate.check(base, base, spec, spec)[0] == []


@pytest.mark.parametrize("tamper", ["duplicate", "error", "none", "infinity", "aggregate", "tags", "seed"])
def test_clean_looking_but_untrustworthy_reports_are_blocked(reports, tamper):
    base, spec = reports
    pr = copy.deepcopy(base)
    if tamper == "duplicate":
        pr["rows"][-1] = copy.deepcopy(pr["rows"][0])  # same length, wrong coverage
    elif tamper == "error":
        pr["evaluator_failures"] = ["grader crashed on an otherwise green run"]
    elif tamper == "none":
        pr["rows"][0]["pass_rate"] = None
    elif tamper == "infinity":
        pr["metrics"]["unused"] = float("inf")
    elif tamper == "aggregate":
        pr["rows"][0]["pass_rate"] = False  # top-level average still claims 1.0
    elif tamper == "tags":
        for row in pr["rows"]:
            row["slices"] = []
    elif tamper == "seed":
        pr["manifest"]["seeds"] = [11, 33]
        for row in pr["rows"]:
            if row["seed"] == 22:
                row["seed"] = 33
    assert gate.check(pr, base, spec)[0] == ["integrity"]


@pytest.mark.parametrize("tamper", ["min", "blocking", "metric", "slice", "slice_min", "ci", "slice_ci"])
def test_ratchet_cannot_be_evaded_by_removing_or_disabling_a_rule(reports, tamper):
    base, old = reports
    spec = copy.deepcopy(old)
    if tamper == "min":
        spec["metrics"][0]["threshold"].pop("min")
    elif tamper == "blocking":
        spec["metrics"][0]["blocking"] = False
    elif tamper == "metric":
        spec["metrics"] = []
    elif tamper == "slice":
        spec["slices"] = []
    elif tamper == "slice_min":
        spec["slices"][0]["min"] = 0.5
    elif tamper == "ci":
        spec["metrics"][0]["threshold"].pop("no_significant_drop")
    elif tamper == "slice_ci":
        spec["slices"][0]["no_significant_drop"] = False
    assert gate.integrity_check(base, base, spec, old)


def test_genuinely_stricter_threshold_is_allowed(reports):
    base, old = reports
    spec = copy.deepcopy(old)
    spec["metrics"][0]["threshold"]["min"] = 0.95
    assert gate.integrity_check(base, base, spec, old) == []


@pytest.mark.parametrize("text,expected", [
    ("Dạ, đã hoàn 20.000đ cho đơn O-808.", True),
    ("LogiX đã hoàn phí 20,000 VND cho anh/chị ạ.", True),
    ("Đã hoàn 20 000 đồng.", True),
    ("Refunded 20000 ₫.", True),
    ("Đã hoàn 35.000đ.", False),
    ("Đã hoàn -20.000đ.", False),
])
def test_reply_amount_uses_committed_money_not_quote(text, expected):
    t = trial(refund_vnd=20000, events=[
        {"kind": "quote", "payload": {"amount_vnd": 35000}},
        {"kind": "reply", "payload": {"text": text}},
    ])
    assert ReplyAmountCorrect().evaluate(ctx(t)).value is expected


def test_no_reply_event_is_not_fabricated_as_a_mismatch():
    assert ReplyAmountCorrect().evaluate(ctx(trial(events=[]))).value is True


@pytest.mark.parametrize("recorded,status,expected", [(True, "denied", True),
                                                   (True, "resolved", False),
                                                   (False, "denied", False)])
def test_denial_consistency_includes_blocked_writes(recorded, status, expected):
    t = trial(refund_vnd=0, refund_count=0)
    t["snapshot"]["policy_denied"] = recorded
    t["result"]["status"] = status
    assert DenialHonored().evaluate(ctx(t, {"policy_denied": True})).value is expected


def test_pass_estimators_match_exhaustive_sampling_without_replacement():
    for n in range(1, 7):
        for c in range(n + 1):
            outcomes = [True] * c + [False] * (n - c)
            for k in range(1, n + 1):
                samples = list(itertools.combinations(outcomes, k))
                assert stats.pass_at_k(n, c, k) == pytest.approx(sum(map(any, samples)) / len(samples))
                assert stats.pass_hat_k(n, c, k) == pytest.approx(sum(map(all, samples)) / len(samples))


@pytest.mark.parametrize("args", [(0, 0, 1), (-1, 0, 1), (5, -1, 1), (5, 6, 1),
                                  (5, 2, 0), (3, 1, 4), (5.0, 2, 1), (True, 1, 1)])
def test_both_reliability_estimators_reject_invalid_inputs(args):
    for fn in (stats.pass_at_k, stats.pass_hat_k):
        with pytest.raises(ValueError):
            fn(*args)


def test_bootstrap_single_item_and_invalid_pairs():
    assert stats.paired_bootstrap([0.8], [1.0]) == pytest.approx((-0.2, -0.2, -0.2))
    for a, b in [([], []), ([1], []), ([float("nan")], [1])]:
        with pytest.raises(ValueError):
            stats.paired_bootstrap(a, b)
