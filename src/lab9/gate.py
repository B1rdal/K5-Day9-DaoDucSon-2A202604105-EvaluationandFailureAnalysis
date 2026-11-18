"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from numbers import Real
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _finite(value) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _ratchet(spec: dict, old: dict) -> list[str]:
    if spec.get("eval_set_version") != old.get("eval_set_version"):
        return []
    problems = []

    def thresholds(new, previous, label):
        for key in ("min", "max", "max_increase"):
            if key in previous and (key not in new or not _finite(new[key])
                    or (new[key] < previous[key] if key == "min" else new[key] > previous[key])):
                problems.append(f"ratchet: {label} loosened {key}")
        if previous.get("no_significant_drop") and not new.get("no_significant_drop"):
            problems.append(f"ratchet: {label} dropped no_significant_drop")

    for section, key in (("metrics", lambda m: m["id"]),
                         ("slices", lambda s: (s["name"], s["metric"]))):
        current = {key(entry): entry for entry in spec.get(section, [])}
        for entry in old.get(section, []):
            ident = key(entry)
            new = current.get(ident)
            if new is None:
                problems.append(f"ratchet: removed {section} {ident}")
                continue
            if entry.get("blocking") and not new.get("blocking"):
                problems.append(f"ratchet: {section} {ident} is no longer blocking")
            if section == "metrics" and entry.get("kind") != new.get("kind"):
                problems.append(f"ratchet: changed kind of {ident}")
            thresholds(new.get("threshold", {}) if section == "metrics" else new,
                       entry.get("threshold", {}) if section == "metrics" else entry,
                       f"{section} {ident}")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems = []
    if base_spec is not None:
        problems.extend(_ratchet(spec, base_spec))
    metric_defs = spec.get("metrics", [])
    mids = [m["id"] for m in metric_defs]
    if len(set(mids)) != len(mids):
        problems.append("duplicate metric definitions")
    slice_ids = [(s["name"], s["metric"]) for s in spec.get("slices", [])]
    if len(set(slice_ids)) != len(slice_ids):
        problems.append("duplicate slice definitions")
    for m in metric_defs:
        for key, val in m.get("threshold", {}).items():
            if key in ("min", "max", "max_increase") and not _finite(val):
                problems.append(f"invalid threshold {m['id']}/{key}")

    def inspect(report, name):
        if not isinstance(report, dict):
            problems.append(f"{name}: report must be an object")
            return None
        manifest, rows, metrics = report.get("manifest"), report.get("rows"), report.get("metrics")
        if not isinstance(manifest, dict) or not isinstance(rows, list) or not isinstance(metrics, dict):
            problems.append(f"{name}: missing manifest, rows or metrics")
            return None
        if report.get("evaluator_failures") != []:
            problems.append(f"{name}: evaluator failures or missing evaluator status")
        for mid in set(metrics) | set(mids):
            if not _finite(metrics.get(mid)):
                problems.append(f"{name}: metric {mid} is missing, nonnumeric or nonfinite")
        count, seeds = manifest.get("items"), manifest.get("seeds")
        if type(count) is not int or count < 1 or not isinstance(seeds, list) or not seeds:
            problems.append(f"{name}: invalid manifest item count/seeds")
            return None
        if any(type(s) is not int for s in seeds) or len(set(seeds)) != len(seeds):
            problems.append(f"{name}: duplicate or invalid manifest seeds")
            return None
        if "seeds" in spec and set(seeds) != set(spec["seeds"]):
            problems.append(f"{name}: manifest seeds differ from the spec")
        if len(rows) != count * len(seeds):
            problems.append(f"{name}: row count is not items x seeds")
        pairs, tags, by_item = [], {}, {}
        row_mids = [mid for mid in mids if mid in GRADERS or
                    any(isinstance(row, dict) and mid in row for row in rows)]
        valid_values = {mid: [] for mid in row_mids}
        costs = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("item_id"), str) or type(row.get("seed")) is not int:
                problems.append(f"{name}: malformed row identity")
                continue
            item, seed = row["item_id"], row["seed"]
            pairs.append((item, seed))
            slices = row.get("slices", [])
            if not isinstance(slices, list) or any(not isinstance(t, str) for t in slices) or len(set(slices)) != len(slices):
                problems.append(f"{name}: invalid slice tags for {item}")
                slices = []
            slice_set = frozenset(slices)
            if item in tags and tags[item] != slice_set:
                problems.append(f"{name}: slice tags differ between seeds for {item}")
            tags[item] = slice_set
            for mid in row_mids:
                value = row.get(mid)
                if not isinstance(value, (bool, int, float)) or value not in (0, 1) or not math.isfinite(value):
                    problems.append(f"{name}: missing/invalid grader value {item}@{seed}/{mid}")
                else:
                    valid_values[mid].append(float(value))
            if isinstance(row.get("pass_rate"), (bool, int, float)) and row["pass_rate"] in (0, 1):
                by_item.setdefault(item, []).append(bool(row["pass_rate"]))
            if "cost" in row or "cost_per_success" in mids:
                if not _finite(row.get("cost")) or row["cost"] < 0:
                    problems.append(f"{name}: invalid/missing row cost {item}@{seed}")
                else:
                    costs.append(row["cost"])
        pair_counts = Counter(pairs)
        if any(n != 1 for n in pair_counts.values()):
            problems.append(f"{name}: duplicate (item, seed) rows")
        if len(tags) != count or set(pairs) != {(it, s) for it in tags for s in seeds}:
            problems.append(f"{name}: incomplete item x seed coverage")
        for m in metric_defs:
            mid = m["id"]
            values = valid_values.get(mid, [])
            if values and len(values) == len(rows) and _finite(metrics.get(mid)):
                expected = sum(values) if m.get("kind") == "safety" else sum(values) / len(values)
                if not math.isclose(metrics[mid], expected, abs_tol=0.000051, rel_tol=1e-9):
                    problems.append(f"{name}: aggregate {mid} disagrees with rows")
        if by_item and sum(map(len, by_item.values())) == len(rows):
            derived = {"pass_5": sum(all(v) for v in by_item.values()) / len(by_item)}
            for mid in metrics:
                if mid.startswith(("pass_at_", "pass_hat_")):
                    prefix, _, suffix = mid.rpartition("_")
                    if not suffix.isdigit():
                        problems.append(f"{name}: malformed reliability metric {mid}")
                        continue
                    fn = stats.pass_at_k if prefix == "pass_at" else stats.pass_hat_k
                    try:
                        derived[mid] = sum(fn(len(v), sum(v), int(suffix)) for v in by_item.values()) / len(by_item)
                    except ValueError:
                        problems.append(f"{name}: undefined reliability metric {mid}")
            passes = sum(sum(v) for v in by_item.values())
            if len(costs) == len(rows) and passes:
                derived["cost_per_success"] = sum(costs) / passes
            for mid, expected in derived.items():
                if mid in metrics and _finite(metrics[mid]) and not math.isclose(metrics[mid], expected, abs_tol=0.000051, rel_tol=1e-9):
                    problems.append(f"{name}: derived metric {mid} disagrees with rows")
        return manifest, set(pairs), tags

    current, previous = inspect(pr, "PR"), inspect(base, "baseline")
    if current and previous:
        pm, pp, pt = current
        bm, bp, bt = previous
        if not pm.get("eval_set_sha") or pm.get("eval_set_sha") != bm.get("eval_set_sha"):
            problems.append("eval_set_sha differs or is missing")
        if pp != bp:
            problems.append("PR (item, seed) set differs from baseline")
        if pt != bt:
            problems.append("PR item slice tags differ from baseline")
        if spec.get("eval_set"):
            from lab9.evalset import load_jsonl, sha12
            path = Path(spec["eval_set"])
            if not path.is_file():
                problems.append("spec eval set file is missing")
            else:
                items = load_jsonl(path)
                expected = {it["item_id"]: frozenset(it.get("slices", [])) for it in items}
                if pm.get("eval_set_sha") != sha12(path) or bm.get("eval_set_sha") != sha12(path):
                    problems.append("report hash differs from the actual eval set")
                if pt != expected or bt != expected:
                    problems.append("item identities/slices differ from the actual eval set")
    return list(dict.fromkeys(problems))


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices", []):
        name, mid = sl["name"], sl["metric"]
        sid = f"slice:{name}/{mid}"
        a, b = per_item(pr, mid, name), per_item(base, mid, name)
        verdict, note = "ok", ""
        value = sum(a.values()) / len(a) if a else None
        if not a or set(a) != set(b):
            verdict = "missing"
        elif "min" in sl and value < sl["min"]:
            verdict = "fail"
        if sl.get("no_significant_drop") and a and set(a) == set(b):
            keys = sorted(a)
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                confidence=bs.get("confidence", 0.95))
            note = f"delta {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        lines.append(f"  {sid:<36} {value!s:<8} {note} {verdict}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid) is not None:
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                               confidence=bs.get("confidence", 0.95))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
