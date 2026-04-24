"""
Evaluation pipeline – runs CICS and naive baseline against the curated dataset,
computes Precision / Recall / F1 / Direction-Accuracy, and writes results.

Usage:
    python eval/evaluate.py [--save results/eval_results.json]
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cics.rules import evaluate_rules
from cics.extractor import extract_resource_changes, load_plan
from dataset.scenarios import SCENARIOS
from dataset.build_plans import plan_path


# ------------------------------------------------------------------------------
# Naive baseline
# ------------------------------------------------------------------------------

def naive_findings(plan: dict) -> list:
    """
    Naive heuristic: flag every resource change.
    - create  → increase/high
    - replace → increase/high
    - update  → uncertain/medium
    - delete  → decrease/medium
    """
    results = []
    for rc in extract_resource_changes(plan):
        actions = rc.get("change", {}).get("actions", [])
        if not actions or actions == ["no-op"]:
            continue
        if "create" in actions and "delete" not in actions:
            direction, sev = "increase", "high"
        elif "delete" in actions and "create" not in actions:
            direction, sev = "decrease", "medium"
        elif "replace" in actions or (
                "delete" in actions and "create" in actions):
            direction, sev = "increase", "high"
        else:  # update
            direction, sev = "uncertain", "medium"
        results.append({
            "rule_id": "NAIVE",
            "category": "Any change",
            "direction": direction,
            "severity": sev,
            "resource_address": rc.get("address", ""),
            "resource_type": rc.get("type", ""),
            "actions": actions,
        })
    return results


# ------------------------------------------------------------------------------
# Metric helpers
# ------------------------------------------------------------------------------

def _f1(p, r):
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def evaluate_tool(scenarios, tool_fn, plan_loader=load_plan):
    """
    tool_fn(plan_dict) -> list of finding dicts (must have 'direction' key).
    Returns aggregated metrics dict.
    """
    tp = fp = fn = tn = 0
    direction_correct = direction_total = 0
    category_stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    per_scenario = []

    for s in scenarios:
        pfile = plan_path(s)
        if not pfile.exists():
            continue
        plan = plan_loader(pfile)
        gt = s["ground_truth"]
        findings = tool_fn(plan)
        has_finding = len(findings) > 0
        cost_impact = gt["is_cost_impacting"]

        if cost_impact and has_finding:
            tp += 1
            cat = gt["category"] or "Unknown"
            category_stats[cat]["tp"] += 1
            # direction accuracy
            for f in findings:
                fd = f.direction if hasattr(f, "direction") else f.get("direction")
                if gt["direction"] and fd == gt["direction"]:
                    direction_correct += 1
                    break
            direction_total += 1
        elif cost_impact and not has_finding:
            fn += 1
            cat = gt["category"] or "Unknown"
            category_stats[cat]["fn"] += 1
        elif not cost_impact and has_finding:
            fp += 1
        else:
            tn += 1

        per_scenario.append({
            "id": s["id"],
            "description": s["description"],
            "is_cost_impacting": cost_impact,
            "findings_count": len(findings),
            "result": (
                "TP" if cost_impact and has_finding else
                "FN" if cost_impact and not has_finding else
                "FP" if not cost_impact and has_finding else "TN"
            ),
            "direction_expected": gt["direction"],
            "direction_got": (
                (findings[0].direction if hasattr(findings[0], "direction")
                 else findings[0].get("direction"))
                if findings else None
            ),
        })

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = _f1(precision, recall)
    dir_acc = direction_correct / direction_total if direction_total > 0 else 0.0

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision * 100, 1),
        "recall": round(recall * 100, 1),
        "f1": round(f1 * 100, 1),
        "direction_accuracy": round(dir_acc * 100, 1),
        "category_stats": dict(category_stats),
        "per_scenario": per_scenario,
    }


def cics_tool(plan: dict):
    findings = []
    for rc in extract_resource_changes(plan):
        findings.extend(evaluate_rules(rc))
    return findings


# ------------------------------------------------------------------------------
# Reporting
# ------------------------------------------------------------------------------

def print_table(name: str, metrics: dict):
    print(f"\n{'-' * 60}")
    print(f"  {name}")
    print(f"{'-' * 60}")
    print(f"  TP={metrics['tp']}  FP={metrics['fp']}  "
          f"FN={metrics['fn']}  TN={metrics['tn']}")
    print(f"  Precision  : {metrics['precision']:6.1f}%")
    print(f"  Recall     : {metrics['recall']:6.1f}%")
    print(f"  F1 Score   : {metrics['f1']:6.1f}%")
    print(f"  Dir. Acc.  : {metrics['direction_accuracy']:6.1f}%")
    print()
    if metrics.get("category_stats"):
        print(f"  {'Category':<30} {'TP':>4} {'FP':>4} {'FN':>4}")
        print(f"  {'-' * 43}")
        for cat, s in sorted(metrics["category_stats"].items()):
            print(f"  {cat:<30} {s['tp']:>4} {s.get('fp', 0):>4} {s['fn']:>4}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", default="results/eval_results.json")
    args = ap.parse_args()

    # Build plans if missing
    from dataset.build_plans import build_all, PLAN_ROOT
    if not PLAN_ROOT.exists() or not any(PLAN_ROOT.rglob("*.json")):
        print("Building plan JSON files first …")
        build_all()

    print(f"\nEvaluating {len(SCENARIOS)} scenarios …")

    cics_metrics = evaluate_tool(SCENARIOS, cics_tool)
    naive_metrics = evaluate_tool(SCENARIOS, naive_findings)

    print_table("CICS (Cost-Impact Change Signals)", cics_metrics)
    print_table("Naive Baseline", naive_metrics)

    # Save
    out_path = Path(args.save)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"cics": cics_metrics, "naive": naive_metrics},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nResults saved → {out_path}")


if __name__ == "__main__":
    main()
