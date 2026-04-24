"""
CICS command-line entry point.

Usage:
    python -m cics.run --plan plan.json
    python -m cics.run --plan plan.json --out findings.json
    python -m cics.run --plan plan.json --explain
"""

import argparse
import json
import sys
from pathlib import Path

from .extractor import load_plan, extract_resource_changes
from .rules import evaluate_rules


def main():
    ap = argparse.ArgumentParser(
        prog="python -m cics.run",
        description="CICS: detect cost-impacting changes in a Terraform plan JSON.",
    )
    ap.add_argument("--plan", required=True, help="Path to terraform show -json output")
    ap.add_argument("--out", default=None, help="Write findings JSON to this file")
    ap.add_argument("--explain", action="store_true",
                    help="Generate AI explanations (requires ANTHROPIC_API_KEY)")
    args = ap.parse_args()

    plan_file = Path(args.plan)
    if not plan_file.exists():
        print(f"Error: plan file not found: {plan_file}", file=sys.stderr)
        sys.exit(1)

    plan = load_plan(plan_file)
    findings = []
    for rc in extract_resource_changes(plan):
        findings.extend(evaluate_rules(rc))

    if args.explain and findings:
        from .explainer import explain_findings_bulk
        findings = explain_findings_bulk(findings)
        out_dicts = findings
    else:
        out_dicts = [f.to_dict() if hasattr(f, "to_dict") else f for f in findings]

    if not findings:
        print("No cost-impacting changes detected.")
    else:
        print(f"\nCICS findings: {len(out_dicts)} signal(s) detected\n")
        for f in out_dicts:
            fd = f if isinstance(f, dict) else f
            print(f"  [{fd.get('rule_id')}] {fd.get('resource_address')}")
            print(f"    Category  : {fd.get('category')}")
            print(f"    Direction : {fd.get('direction')}  Severity: {fd.get('severity')}")
            ev = fd.get('evidence', {})
            for k, v in ev.items():
                print(f"    {k}: {v}")
            if fd.get("explanation"):
                print(f"\n    {fd['explanation']}\n")
            print()

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_dicts, indent=2), encoding="utf-8")
        print(f"Findings written to {out_path}")


if __name__ == "__main__":
    main()
