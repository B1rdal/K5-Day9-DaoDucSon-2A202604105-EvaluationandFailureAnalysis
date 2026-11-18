"""Capture v2 policy, principal-scope and adversarial trace examples."""

import json
from pathlib import Path
import tempfile

from lab8.console import utf8_stdio
from lab8.shapes import SHAPES
from lab9 import variants
from lab9.eval import load_spec, load_world, make_task
from lab9.variant_agent import make_shape


def main():
    utf8_stdio()
    spec = load_spec(Path("config/metric_spec_v2.yaml"))
    world, claims = load_world(spec)
    labels = json.loads(Path(spec["labels"]).read_text(encoding="utf-8"))
    variants.register()
    SHAPES["v2_misreport"] = make_shape("v2_misreport", {"no_override", "misreport"})
    examples = [("fixed", c, 11) for c in ("C-110", "C-113", "C-114", "C-105", "C-109")]
    examples += [("slice_regression", "C-105", 11), ("v2_misreport", "C-109", 11)]
    observations = []
    with tempfile.TemporaryDirectory(prefix="lab9-v2-evidence-", ignore_cleanup_errors=True) as folder:
        for shape, claim_id, seed in examples:
            trial = make_task(shape, world, claims, labels, Path(folder))({"claim_id": claim_id, "seed": seed})
            observations.append({"shape": shape, "claim_id": claim_id, "seed": seed,
                                 "result": trial["result"], "snapshot": trial["snapshot"],
                                 "unexpected_rows": trial["unexpected_rows"],
                                 "lab8_pass": trial["lab8_pass"], "lab8_reason": trial["lab8_reason"],
                                 "events": [{"step": n, **e} for n, e in enumerate(trial["events"], 1)]})
    out = Path("../docs/evidence/v2_traces.json")
    out.write_text(json.dumps({"generator": "python -m scripts.build_v2_evidence",
                               "observations": observations}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(observations)} v2 observations")


if __name__ == "__main__":
    main()
