"""M2 classifier edge cases and rejection of misleading calibration inputs."""

import math
from pathlib import Path

import pytest

from lab9 import stats
from lab9.judge import calibrate

pytestmark = pytest.mark.student


def test_fail_is_positive_even_when_labels_are_swapped():
    assert stats.confusion(["FAIL", "PASS"], ["PASS", "FAIL"]) == {
        "tp": 0, "fp": 1, "fn": 1, "tn": 0,
    }
    assert stats.cohen_kappa(["FAIL", "PASS"], ["PASS", "FAIL"]) == -1


def test_constant_pass_judge_has_zero_recall_on_mixed_labels():
    human, judge = ["FAIL", "PASS"], ["PASS", "PASS"]
    assert stats.precision_recall(human, judge) == (0.0, 0.0)
    assert stats.cohen_kappa(human, judge) == 0.0
    assert stats.precision_recall([], []) == (0.0, 0.0)


@pytest.mark.parametrize("human,judge", [(["PASS"], []), (["UNKNOWN"], ["PASS"])])
def test_confusion_rejects_unpaired_or_invalid_labels(human, judge):
    with pytest.raises(ValueError):
        stats.confusion(human, judge)


@pytest.mark.parametrize("labels", [[], ["PASS"] * 3, ["FAIL"] * 3])
def test_kappa_rejects_undefined_agreement(labels):
    with pytest.raises(ValueError):
        stats.cohen_kappa(labels, labels)


@pytest.mark.parametrize("rates", [
    (0.2, 0.5, 0.5), (0.2, 0.1, 0.2),
    (-0.1, 0.8, 0.9), (0.2, 1.1, 0.9), (math.nan, 0.8, 0.9),
])
def test_rogan_gladen_rejects_unusable_calibration(rates):
    with pytest.raises(ValueError):
        stats.rogan_gladen(*rates)


def test_rogan_gladen_upper_clip():
    assert stats.rogan_gladen(1.0, 0.8, 0.9) == 1.0


def test_helpful_high_precision_does_not_hide_low_recall():
    result = calibrate(Path("data/eval/judge_helpful_public.csv"))
    assert result["confusion"] == {"tp": 9, "fp": 0, "fn": 21, "tn": 70}
    assert result["precision"] == 1.0
    assert result["recall"] == 0.3
    assert result["kappa"] == 0.375
    assert not result["passed"]


def test_undefined_kappa_rejects_judge_without_crashing(tmp_path):
    csv_path = tmp_path / "constant.csv"
    csv_path.write_text("item_id,reply,human,judge\nx,hello,PASS,PASS\n", encoding="utf-8")
    result = calibrate(csv_path)
    assert math.isnan(result["kappa"])
    assert result["corrected_fail_rate"] is None
    assert not result["passed"]


def test_empty_calibration_rejected(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("item_id,reply,human,judge\n", encoding="utf-8")
    with pytest.raises(ValueError, match="at least one"):
        calibrate(csv_path)
