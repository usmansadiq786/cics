"""
Full CICS pipeline runner.

Steps:
  1. Build plan JSON dataset from scenarios
  2. Run evaluation (CICS vs naive baseline)
  3. Optionally run AI explainer on a sample of findings

Usage:
    python run_all.py               # build + evaluate
    python run_all.py --explain     # also run AI explainer (needs ANTHROPIC_API_KEY)
    python run_all.py --save-report results/report.json
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def step_build():
    from dataset.build_plans import build_all
    print("\n[1/3] Building plan JSON dataset …")
    build_all()


def step_evaluate(save_path: str):
    from eval.evaluate import main as eval_main
    import sys
    sys.argv = ["evaluate.py", "--save", save_path]
    print("\n[2/3] Running evaluation …")
    eval_main()


def step_explain(results_path: str, n_samples: int = 15):
    from cics.rules import evaluate_rules
    from cics.extractor import extract_resource_changes, load_plan
    from cics.explainer import explain_findings_bulk
    from dataset.scenarios import SCENARIOS
    from dataset.build_plans import plan_path

    print(f"\n[3/3] Running AI explainer on up to {n_samples} findings …")

    findings_to_explain = []
    for s in SCENARIOS[:n_samples]:
        pf = plan_path(s)
        if not pf.exists():
            continue
        plan = load_plan(pf)
        for rc in extract_resource_changes(plan):
            for f in evaluate_rules(rc):
                findings_to_explain.append(f)
                if len(findings_to_explain) >= n_samples:
                    break
        if len(findings_to_explain) >= n_samples:
            break

    save_explanations = Path(results_path).parent / "explanations.json"
    explained = explain_findings_bulk(findings_to_explain,
                                      save_path=str(save_explanations))
    print(f"  Generated {len(explained)} explanations -> {save_explanations}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--explain", action="store_true",
                    help="Also run AI explainer (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--save-report", default="results/eval_results.json")
    args = ap.parse_args()

    step_build()
    step_evaluate(args.save_report)
    if args.explain:
        step_explain(args.save_report)

    print("\nDone. Review results in:", Path(args.save_report).parent)


if __name__ == "__main__":
    main()
