"""
Parse a Terraform plan JSON file and yield resource_change dicts
that are suitable for rule evaluation.
"""

import json
from pathlib import Path


def load_plan(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def extract_resource_changes(plan: dict) -> list:
    """
    Return the list of resource_change dicts from a Terraform plan JSON.
    Skips no-op changes.
    """
    out = []
    for rc in plan.get("resource_changes", []) or []:
        change = rc.get("change", {}) or {}
        actions = change.get("actions", []) or []
        if actions == ["no-op"] or not actions:
            continue
        out.append(rc)
    return out
