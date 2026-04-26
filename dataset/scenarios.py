"""
Dynamically generates CICS evaluation scenarios from real Terraform base plans.

Base plans are produced by dataset/select_examples.py and stored under
dataset/plans/base/<repo>/<example>/base.json.

For each plan:
  - One cost-impacting scenario per cost-relevant resource type found
    (before = real deployed values, after = a single cost-changing attribute)
  - One false-positive scenario per plan (tags-only change on a non-cost resource)

If dataset/plans/base/ does not exist, run:
    python dataset/select_examples.py

repo field
----------
The "repo" key in each scenario matches the folder name produced by
examples/clone_repos.sh (GitHub org/name with "/" replaced by "__").
SOURCE_REPOS below maps each folder name to its GitHub URL.
Clone the source repos to browse the real .tf files each scenario was
derived from:
    bash examples/clone_repos.sh     # clones into examples/repos/
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Source repo mapping — loaded from examples/sample_repos.txt
# ---------------------------------------------------------------------------

def _load_source_repos() -> dict:
    txt = Path(__file__).resolve().parents[1] / "examples" / "sample_repos.txt"
    result = {}
    for line in txt.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            full_name, url = parts[0], parts[1]
            result[full_name.replace("/", "__")] = url.removesuffix(".git")
    return result


SOURCE_REPOS = _load_source_repos()


# ---------------------------------------------------------------------------
# Instance-type bump helpers (same family/prefix, adjacent size)
# ---------------------------------------------------------------------------

_EC2_SIZES = [
    "nano", "micro", "small", "medium", "large",
    "xlarge", "2xlarge", "4xlarge", "8xlarge", "12xlarge", "16xlarge",
]

_GCP_VCPUS  = [1, 2, 4, 8, 16, 32, 64]
_GCP_SQL_TIERS = [
    "db-f1-micro", "db-g1-small",
    "db-n1-standard-1", "db-n1-standard-2", "db-n1-standard-4", "db-n1-standard-8",
    "db-n1-highmem-2",  "db-n1-highmem-4",  "db-n1-highmem-8",  "db-n1-highmem-16",
]


def _bump_ec2(it: str, direction: int) -> str | None:
    """Bump an EC2/RDS/ElastiCache instance type one size up (+1) or down (-1)."""
    if not it:
        return None
    prefix = ""
    core   = it
    for pfx in ("db.", "cache."):
        if it.startswith(pfx):
            prefix, core = pfx, it[len(pfx):]
            break
    parts = core.split(".", 1)
    if len(parts) != 2:
        return None
    family, size = parts
    if size not in _EC2_SIZES:
        return None
    idx     = _EC2_SIZES.index(size)
    new_idx = idx + direction
    if 0 <= new_idx < len(_EC2_SIZES):
        return f"{prefix}{family}.{_EC2_SIZES[new_idx]}"
    return None


def _bump_gcp(mt: str, direction: int) -> str | None:
    """Bump a GCP machine type one step up (+1) or down (-1)."""
    if not mt:
        return None
    parts = mt.rsplit("-", 1)
    if len(parts) != 2:
        return None
    prefix, last = parts
    _special_up = {"micro": "small", "small": "medium", "medium": "2"}
    _special_dn = {"small": "micro", "medium": "small"}
    if last in _special_up and direction > 0:
        return f"{prefix}-{_special_up[last]}"
    if last in _special_dn and direction < 0:
        return f"{prefix}-{_special_dn[last]}"
    if last.isdigit():
        vcpus = int(last)
        if vcpus in _GCP_VCPUS:
            ni = _GCP_VCPUS.index(vcpus) + direction
            if 0 <= ni < len(_GCP_VCPUS):
                return f"{prefix}-{_GCP_VCPUS[ni]}"
    return None


def _bump_gcp_sql(tier: str, direction: int) -> str | None:
    if not tier or tier not in _GCP_SQL_TIERS:
        return "db-n1-standard-4" if direction > 0 else None
    ni = _GCP_SQL_TIERS.index(tier) + direction
    if 0 <= ni < len(_GCP_SQL_TIERS):
        return _GCP_SQL_TIERS[ni]
    return None


# ---------------------------------------------------------------------------
# Sensible attribute defaults when a value is null/missing in the base plan
# ---------------------------------------------------------------------------

_ATTR_DEFAULTS = {
    "instance_type":     "t3.micro",
    "instance_class":    "db.t4g.large",
    "node_type":         "cache.t3.micro",
    "machine_type":      "n1-standard-2",
    "tier":              "db-n1-standard-2",
    "min_size":          1,
    "max_size":          3,
    "min_capacity":      1,
    "max_capacity":      10,
    "min_node_count":    1,
    "max_node_count":    3,
    "desired_capacity":  1,
    "allocated_storage": 20,
    "volume_size":       50,
    "disk_size":         10,
    "multi_az":          False,
    "availability_type": "ZONAL",
    "storage_type":      "gp2",
    "volume_type":       "gp2",
    "replica_count":     1,
}


# ---------------------------------------------------------------------------
# Change templates per resource type
# Each entry is tried in order; first one that produces a valid change is used.
#
# Fields:
#   rule_id, category, direction, severity  — copied to ground_truth
#   action     — "update" (default) | "create" | "replace"
#   attribute  — for update actions: which attribute to change
#   transform  — callable(before_value) -> after_value
#   before_value / after_value  — explicit values instead of transform
# ---------------------------------------------------------------------------

CHANGE_TEMPLATES: dict[str, list[dict]] = {
    # --- EC2 ---------------------------------------------------------------
    "aws_instance": [
        {"rule_id": "C1", "category": "Compute sizing",   "direction": "increase",
         "severity": "high",   "attribute": "instance_type",
         "transform": lambda v: _bump_ec2(v, +1)},
        {"rule_id": "C2", "category": "Compute sizing",   "direction": "decrease",
         "severity": "high",   "attribute": "instance_type",
         "transform": lambda v: _bump_ec2(v, -1)},
    ],
    "aws_launch_template": [
        {"rule_id": "C1", "category": "Compute sizing",   "direction": "increase",
         "severity": "high",   "attribute": "instance_type",
         "transform": lambda v: _bump_ec2(v, +1)},
    ],
    "aws_launch_configuration": [
        {"rule_id": "C1", "category": "Compute sizing",   "direction": "increase",
         "severity": "high",   "attribute": "instance_type",
         "transform": lambda v: _bump_ec2(v, +1)},
    ],
    # --- RDS ---------------------------------------------------------------
    "aws_db_instance": [
        {"rule_id": "C1",  "category": "Compute sizing",          "direction": "increase",
         "severity": "high",   "attribute": "instance_class",
         "transform": lambda v: _bump_ec2(v, +1)},
        {"rule_id": "A1",  "category": "Availability/replication", "direction": "increase",
         "severity": "high",   "attribute": "multi_az",
         "before_value": False, "after_value": True},
        {"rule_id": "ST1", "category": "Storage capacity",         "direction": "increase",
         "severity": "high",   "attribute": "allocated_storage",
         "transform": lambda v: max(int(v or 20) * 5, 100)},
        {"rule_id": "ST2", "category": "Storage tier",             "direction": "increase",
         "severity": "medium", "attribute": "storage_type",
         "before_value": "gp2", "after_value": "io1"},
        {"rule_id": "M2",  "category": "Replacement spike",        "direction": "increase",
         "severity": "high",   "action": "replace"},
    ],
    "aws_rds_cluster": [
        {"rule_id": "M1",  "category": "Managed service intro",    "direction": "increase",
         "severity": "high",   "action": "create"},
        {"rule_id": "A1",  "category": "Availability/replication", "direction": "increase",
         "severity": "high",   "attribute": "replica_count",
         "transform": lambda v: (int(v or 1)) + 2},
        {"rule_id": "M2",  "category": "Replacement spike",        "direction": "increase",
         "severity": "high",   "action": "replace"},
    ],
    "aws_rds_cluster_instance": [
        {"rule_id": "C1",  "category": "Compute sizing",           "direction": "increase",
         "severity": "high",   "attribute": "instance_class",
         "transform": lambda v: _bump_ec2(v, +1)},
    ],
    # --- Auto Scaling / App Autoscaling ------------------------------------
    "aws_autoscaling_group": [
        {"rule_id": "S1",  "category": "Scaling bounds",           "direction": "increase",
         "severity": "high",   "attribute": "min_size",
         "transform": lambda v: (int(v or 1)) + 2},
        {"rule_id": "S2",  "category": "Scaling bounds",           "direction": "increase",
         "severity": "medium", "attribute": "max_size",
         "transform": lambda v: (int(v or 3)) * 4},
        {"rule_id": "S3",  "category": "Scaling bounds",           "direction": "decrease",
         "severity": "medium", "attribute": "min_size",
         "transform": lambda v: max(1, int(v or 3) - 2)},
    ],
    "aws_appautoscaling_target": [
        {"rule_id": "S1",  "category": "Scaling bounds",           "direction": "increase",
         "severity": "high",   "attribute": "min_capacity",
         "transform": lambda v: (int(v or 1)) + 3},
        {"rule_id": "S2",  "category": "Scaling bounds",           "direction": "increase",
         "severity": "medium", "attribute": "max_capacity",
         "transform": lambda v: (int(v or 10)) * 5},
    ],
    # --- Storage -----------------------------------------------------------
    "aws_ebs_volume": [
        {"rule_id": "ST1", "category": "Storage capacity",         "direction": "increase",
         "severity": "high",   "attribute": "volume_size",
         "transform": lambda v: (int(v or 50)) * 4},
        {"rule_id": "ST2", "category": "Storage tier",             "direction": "increase",
         "severity": "medium", "attribute": "volume_type",
         "before_value": "gp2", "after_value": "io1"},
    ],
    # --- Networking --------------------------------------------------------
    "aws_nat_gateway": [
        {"rule_id": "N1",  "category": "Networking gateway",       "direction": "increase",
         "severity": "high",   "action": "create"},
    ],
    "aws_lb": [
        {"rule_id": "N2",  "category": "Load balancing",           "direction": "increase",
         "severity": "high",   "action": "create"},
        {"rule_id": "M2",  "category": "Replacement spike",        "direction": "increase",
         "severity": "high",   "action": "replace"},
    ],
    "aws_alb": [
        {"rule_id": "N2",  "category": "Load balancing",           "direction": "increase",
         "severity": "high",   "action": "create"},
    ],
    "aws_cloudfront_distribution": [
        {"rule_id": "N3",  "category": "Data transfer driver",     "direction": "uncertain",
         "severity": "medium", "action": "create"},
    ],
    # --- Managed services --------------------------------------------------
    "aws_elasticache_cluster": [
        {"rule_id": "M1",  "category": "Managed service intro",    "direction": "increase",
         "severity": "high",   "action": "create"},
        {"rule_id": "C1",  "category": "Compute sizing",           "direction": "increase",
         "severity": "high",   "attribute": "node_type",
         "transform": lambda v: _bump_ec2(v, +1)},
    ],
    "aws_elasticache_replication_group": [
        {"rule_id": "M1",  "category": "Managed service intro",    "direction": "increase",
         "severity": "high",   "action": "create"},
    ],
    "aws_sqs_queue": [
        {"rule_id": "M1",  "category": "Managed service intro",    "direction": "increase",
         "severity": "high",   "action": "create"},
    ],
    # --- GCP ---------------------------------------------------------------
    "google_compute_instance": [
        {"rule_id": "C1",  "category": "Compute sizing",           "direction": "increase",
         "severity": "high",   "attribute": "machine_type",
         "transform": lambda v: _bump_gcp(v, +1)},
    ],
    "google_compute_instance_template": [
        {"rule_id": "C1",  "category": "Compute sizing",           "direction": "increase",
         "severity": "high",   "attribute": "machine_type",
         "transform": lambda v: _bump_gcp(v, +1)},
    ],
    "google_sql_database_instance": [
        {"rule_id": "C1",  "category": "Compute sizing",           "direction": "increase",
         "severity": "high",   "attribute": "tier",
         "transform": lambda v: _bump_gcp_sql(v, +1)},
        {"rule_id": "A1",  "category": "Availability/replication", "direction": "increase",
         "severity": "high",   "attribute": "availability_type",
         "before_value": "ZONAL", "after_value": "REGIONAL"},
        {"rule_id": "ST1", "category": "Storage capacity",         "direction": "increase",
         "severity": "high",   "attribute": "disk_size",
         "transform": lambda v: (int(v or 10)) * 10},
        {"rule_id": "M1",  "category": "Managed service intro",    "direction": "increase",
         "severity": "high",   "action": "create"},
    ],
    "google_container_node_pool": [
        {"rule_id": "S1",  "category": "Scaling bounds",           "direction": "increase",
         "severity": "high",   "attribute": "min_node_count",
         "transform": lambda v: (int(v or 1)) + 3},
        {"rule_id": "S2",  "category": "Scaling bounds",           "direction": "increase",
         "severity": "medium", "attribute": "max_node_count",
         "transform": lambda v: (int(v or 3)) * 4},
    ],
    "google_compute_router_nat": [
        {"rule_id": "N1",  "category": "Networking gateway",       "direction": "increase",
         "severity": "high",   "action": "create"},
    ],
    "google_compute_forwarding_rule": [
        {"rule_id": "N2",  "category": "Load balancing",           "direction": "increase",
         "severity": "high",   "action": "create"},
    ],
    "google_redis_instance": [
        {"rule_id": "M1",  "category": "Managed service intro",    "direction": "increase",
         "severity": "high",   "action": "create"},
    ],
    "google_pubsub_topic": [
        {"rule_id": "M1",  "category": "Managed service intro",    "direction": "increase",
         "severity": "high",   "action": "create"},
    ],
}


# ---------------------------------------------------------------------------
# Dynamic scenario generation
# ---------------------------------------------------------------------------

def _generate_scenarios() -> list[dict]:
    base_dir = Path(__file__).parent / "plans" / "base"
    if not base_dir.exists():
        print(
            "[scenarios.py] dataset/plans/base/ not found. "
            "Run: python dataset/select_examples.py",
            file=sys.stderr,
        )
        return []

    scenarios, counter = [], 1

    for plan_path in sorted(base_dir.rglob("base.json")):
        parts = plan_path.relative_to(base_dir).parts
        if len(parts) < 3:
            continue
        repo, example = parts[0], parts[1]

        try:
            plan = json.loads(plan_path.read_text())
        except Exception:
            continue

        rcs = plan.get("resource_changes", [])
        used_types: set[str] = set()

        # ---- cost-impacting scenarios ------------------------------------
        for rc in rcs:
            rtype = rc.get("type", "")
            if rtype in used_types or rtype not in CHANGE_TEMPLATES:
                continue

            after_vals = (rc.get("change") or {}).get("after") or {}

            for tmpl in CHANGE_TEMPLATES[rtype]:
                action = tmpl.get("action", "update")

                if action == "create":
                    before, after, actions = None, after_vals, ["create"]
                    desc = f"{rtype} created"

                elif action == "replace":
                    before = after_vals
                    after  = after_vals
                    actions = ["delete", "create"]
                    desc = f"{rtype} replaced"

                else:  # update
                    attr = tmpl["attribute"]
                    cur  = after_vals.get(attr)

                    if "before_value" in tmpl:
                        bval, aval = tmpl["before_value"], tmpl["after_value"]
                    else:
                        if cur is None:
                            cur = _ATTR_DEFAULTS.get(attr)
                        if cur is None:
                            continue
                        aval = tmpl["transform"](cur)
                        if aval is None or aval == cur:
                            continue
                        bval = cur

                    before  = {**after_vals, attr: bval}
                    after   = {**after_vals, attr: aval}
                    actions = ["update"]
                    desc    = f"{rtype}: {attr} {bval} -> {aval}"

                scenarios.append({
                    "id": f"S{counter:03d}",
                    "repo": repo,
                    "example": example,
                    "description": desc,
                    "ground_truth": {
                        "is_cost_impacting": True,
                        "direction":         tmpl["direction"],
                        "category":          tmpl["category"],
                        "expected_rule_ids": [tmpl["rule_id"]],
                    },
                    "resource_changes": [{
                        "address": rc.get("address", f"{rtype}.this"),
                        "type":    rtype,
                        "change":  {"actions": actions, "before": before, "after": after},
                    }],
                })
                counter += 1
                used_types.add(rtype)
                break  # one scenario per resource type per plan

        # ---- false-positive scenario (one per plan) ----------------------
        for rc in rcs:
            rtype     = rc.get("type", "")
            after_vals = (rc.get("change") or {}).get("after") or {}
            if not after_vals or rtype in CHANGE_TEMPLATES:
                continue
            scenarios.append({
                "id": f"S{counter:03d}",
                "repo": repo,
                "example": example,
                "description": f"{rtype}: tags-only update — no cost impact",
                "ground_truth": {
                    "is_cost_impacting": False,
                    "direction":         None,
                    "category":          None,
                    "expected_rule_ids": [],
                },
                "resource_changes": [{
                    "address": rc.get("address", f"{rtype}.this"),
                    "type":    rtype,
                    "change":  {
                        "actions": ["update"],
                        "before":  {**after_vals, "tags": {"env": "prod"}},
                        "after":   {**after_vals, "tags": {"env": "staging"}},
                    },
                }],
            })
            counter += 1
            break  # one FP per plan

    if not scenarios:
        print(
            "[scenarios.py] No scenarios generated. "
            "Run: python dataset/select_examples.py",
            file=sys.stderr,
        )
    else:
        cost    = sum(1 for s in scenarios if s["ground_truth"]["is_cost_impacting"])
        noncost = len(scenarios) - cost
        print(
            f"[scenarios.py] {len(scenarios)} scenarios "
            f"({cost} cost-impacting, {noncost} non-cost)."
        )

    return scenarios


SCENARIOS = _generate_scenarios()
