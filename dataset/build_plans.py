"""
Generate Terraform plan JSON files from SCENARIOS definitions.
Each file is a valid `terraform show -json` format document.

The scenarios in scenarios.py were derived from real Terraform module
repositories listed in examples/sample_repos.txt. To browse the source
.tf files that each scenario's attribute names and values were taken from:
    bash examples/clone_repos.sh     # clones all 16 repos into examples/repos/

Usage:
    python dataset/build_plans.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dataset.scenarios import SCENARIOS

PLAN_ROOT = Path(__file__).parent / "plans"
TF_VERSION = "1.7.5"
FORMAT_VERSION = "1.0"


def scenario_to_plan(scenario: dict) -> dict:
    return {
        "format_version": FORMAT_VERSION,
        "terraform_version": TF_VERSION,
        "variables": {},
        "planned_values": {},
        "resource_changes": [
            {
                "address": rc.get("address", ""),
                "module_address": rc.get("address", "").rsplit(".", 2)[0]
                if "." in rc.get("address", "") else "",
                "mode": "managed",
                "type": rc.get("type", ""),
                "name": rc.get("address", "").rsplit(".", 1)[-1],
                "provider_name": _provider(rc.get("type", "")),
                "change": {
                    "actions": rc["change"]["actions"],
                    "before": rc["change"].get("before"),
                    "after": rc["change"].get("after"),
                    "after_unknown": {},
                },
            }
            for rc in scenario["resource_changes"]
        ],
    }


def _provider(rtype: str) -> str:
    if rtype.startswith("google_"):
        return "registry.terraform.io/hashicorp/google"
    if rtype.startswith("azurerm_"):
        return "registry.terraform.io/hashicorp/azurerm"
    return "registry.terraform.io/hashicorp/aws"


def plan_path(scenario: dict) -> Path:
    repo = scenario["repo"]
    example = scenario["example"]
    sid = scenario["id"]
    return PLAN_ROOT / repo / example / f"{sid}.json"


def build_all():
    for s in SCENARIOS:
        out = plan_path(s)
        out.parent.mkdir(parents=True, exist_ok=True)
        plan = scenario_to_plan(s)
        out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Built {len(SCENARIOS)} plan JSON files under {PLAN_ROOT}")


if __name__ == "__main__":
    build_all()
