"""Dataset fingerprints must not change between Windows and Linux checkouts."""

import hashlib
import json
from pathlib import Path

import pytest

from lab9 import evalset

pytestmark = pytest.mark.student


def test_both_builders_write_identical_lf_bytes_on_every_platform(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = Path("claims.jsonl")
    source.write_text(json.dumps({"claim_id": "C-001", "matrix_id": "T01",
                                  "expected": {"refund_vnd": 35000}}), encoding="utf-8")
    evalset.build(source)
    pack, mapping = Path("pack.json"), Path("map.yaml")
    pack.write_text('{"claims": []}', encoding="utf-8")
    mapping.write_text('{}', encoding="utf-8")
    evalset.build_v2(pack=pack, fm_map=mapping)
    for path in (evalset.ITEMS, evalset.ITEMS_V2):
        raw = path.read_bytes()
        assert b"\r" not in raw
        assert raw.endswith(b"\n")
        assert evalset.sha12(path) == hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()[:12]
