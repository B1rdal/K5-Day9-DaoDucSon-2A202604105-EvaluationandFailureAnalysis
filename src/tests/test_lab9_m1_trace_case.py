"""Regression evidence for the original swarm's ticket-vs-DB boundary."""

import pytest

from lab9.trace_case import investigate

pytestmark = pytest.mark.student


@pytest.mark.parametrize("shape,seed,expected_pass", [
    ("swarm", 55, False), ("swarm", 11, True), ("fixed", 55, True),
])
def test_authoritative_delay_boundary(shape, seed, expected_pass):
    case = investigate(shape, "C-002", seed)
    trial = case["trial"]
    assert trial["lab8_pass"] is expected_pass
    assert trial["events"][1]["payload"]["lookup_order"]["order"]["delay_days"] == 2
    if expected_pass:
        assert trial["snapshot"]["refund_vnd"] == case["label"]["refund_vnd"] == 0
        assert trial["result"]["status"] == "denied"
        assert not any(e["kind"] == "model_override" for e in trial["events"])
    else:
        assert trial["events"][2]["kind"] == "model_override"
        assert trial["events"][2]["payload"]["delay_days"] == 5
        assert trial["snapshot"]["refund_vnd"] == 20000
        assert trial["snapshot"]["refund_vnd"] != case["label"]["refund_vnd"]
