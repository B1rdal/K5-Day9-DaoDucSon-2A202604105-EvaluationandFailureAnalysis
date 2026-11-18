"""Rebuild the submission and verify Core, Advanced and Expert evidence.

Run from src/: python -m scripts.verify_lab9
Only this script and the supplied CLIs generate reports; none are hand-edited.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

from lab8.console import utf8_stdio

SRC = Path(__file__).resolve().parents[1]
ROOT = SRC.parent


def main():
    utf8_stdio()
    os.chdir(SRC)
    os.environ["PYTHONUTF8"] = "1"
    records = []
    logs = []
    out = Path("reports")
    out.mkdir(exist_ok=True)

    def save():
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        (out / "submission_checks.json").write_text(json.dumps({
            "implementation_commit": commit, "commands": records,
            "passed": all(r["exit_code"] == r["expected_exit"] for r in records),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        evidence = ROOT / "docs/evidence/final_checks.txt"
        evidence.write_text("\n".join(logs), encoding="utf-8")

    def record(command, status, expected, output):
        records.append({"command": command, "exit_code": status, "expected_exit": expected})
        logs.append(f"$ {command}\n{output.rstrip()}\n[exit {status}; expected {expected}]\n")
        print(logs[-1], flush=True)
        save()
        if status != expected:
            raise RuntimeError(f"Unexpected exit status for {command}")

    def run(module, *args, expected=0):
        result = subprocess.run([sys.executable, "-m", module, *args], capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        record("python -m " + " ".join((module, *args)), result.returncode, expected,
               result.stdout + result.stderr)

    for version, filename in (("v1", "metric_spec.yaml"), ("v2", "metric_spec_v2.yaml")):
        policy = subprocess.check_output(["git", "show", f"origin/main:src/config/{filename}"])
        (out / f"base_policy_{version}.yaml").write_bytes(policy)

    run("lab9.smoke")
    run("pytest", "-q", "-m", "student", "-o", "addopts=", "-k", "lab9")
    run("pytest", "-q")
    run("lab9.evalset", "--build", "--check")
    run("lab9.evalset", "--v2", "--build")
    run("lab9.judge", "--csv", "data/eval/judge_tone_public.csv", "--audit", "10")
    run("lab9.judge", "--csv", "data/eval/judge_helpful_public.csv", "--audit", "8", expected=1)
    run("lab9.mutation", "--detect")

    for version, filename in (("v1", "metric_spec.yaml"), ("v2", "metric_spec_v2.yaml")):
        spec, baseline = f"config/{filename}", f"reports/baseline_{version}.json"
        policy = f"reports/base_policy_{version}.yaml"
        run("lab9.eval", "--shape", "swarm", "--spec", spec, "--out", baseline)
        run("lab9.gate", "--pr", baseline, "--baseline", baseline, "--spec", spec, "--base-spec", policy)
        cases = [("fixed", 0), ("seeded_regression", 1)]
        if version == "v2":
            cases += [("honest_refactor", 0), ("slice_regression", 1), ("flaky_regression", 1)]
        for shape, expected in cases:
            report = f"reports/eval_{shape}{'_v2' if version == 'v2' and shape != 'slice_regression' else ''}.json"
            run("lab9.eval", "--shape", shape, "--spec", spec, "--out", report)
            run("lab9.gate", "--pr", report, "--baseline", baseline, "--spec", spec,
                "--base-spec", policy, expected=expected)

    run("lab9.eval", "--shape", "swarm", "--out", "reports/eval_pr.json")
    run("lab9.ci_check", "--pr", "reports/eval_pr.json", "--baseline", "reports/baseline_v1.json")
    run("lab9.mutation", "--spec", "config/metric_spec_v2.yaml", "--baseline", "reports/baseline_v2.json",
        "--base-spec", "reports/base_policy_v2.yaml")
    run("lab9.mutation", "--spec", "config/metric_spec_v2.yaml", "--aa", "66,77,88,99,110")
    run("lab9.traps", "--pr", "reports/eval_slice_regression.json", "--baseline", "reports/baseline_v2.json",
        "--spec", "config/metric_spec_v2.yaml")
    for name in ("evaluator_errors_as_nan", "dropped_failing_rows", "cherry_picked_seeds", "loosened_spec"):
        spec = f"reports/traps/{name}.spec.yaml" if name == "loosened_spec" else "config/metric_spec_v2.yaml"
        run("lab9.gate", "--pr", f"reports/traps/{name}.json", "--baseline", "reports/baseline_v2.json",
            "--spec", spec, "--base-spec", "config/metric_spec_v2.yaml", expected=1)

    # Additional behavior-based probes: no public variant-name special cases.
    from lab8.shapes import SHAPES
    from lab9 import gate
    from lab9.eval import main as eval_main, load_spec
    from lab9.variant_agent import make_shape
    for name, bugs, expected in (
        ("quiet_fact_error", {"no_override", "quiet_override"}, 1),
        ("reply_mismatch_probe", {"no_override", "misreport"}, 1),
    ):
        SHAPES[name] = make_shape(name, bugs)
        buffer = io.StringIO()
        path = f"reports/eval_{name}_v2.json"
        with contextlib.redirect_stdout(buffer):
            code = eval_main(["--shape", name, "--spec", "config/metric_spec_v2.yaml", "--out", path])
        record(f"lab9.eval {name} (runtime-only probe)", code, 0, buffer.getvalue())
        run("lab9.gate", "--pr", path, "--baseline", "reports/baseline_v2.json",
            "--spec", "config/metric_spec_v2.yaml", expected=expected)

    # Green-run evidence attacks must fail even if no regression is present.
    base = json.loads(Path("reports/baseline_v2.json").read_text(encoding="utf-8"))
    spec = load_spec(Path("config/metric_spec_v2.yaml"))
    import copy
    for attack in ("duplicate_row", "green_evaluator_error", "slice_relabel"):
        pr = copy.deepcopy(base)
        if attack == "duplicate_row":
            pr["rows"][-1] = copy.deepcopy(pr["rows"][0])
        elif attack == "green_evaluator_error":
            pr["evaluator_failures"] = ["synthetic evaluator error on green rows"]
        else:
            for row in pr["rows"]:
                row["slices"] = []
        blocked, lines = gate.check(pr, base, spec)
        record(f"integrity probe: {attack}", 1 if blocked else 0, 1, "\n".join(lines))
    print(f"Verified {len(records)} commands/probes with their expected exit statuses.", flush=True)


if __name__ == "__main__":
    main()
