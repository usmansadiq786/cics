"""
Prepares realistic Terraform examples for the CICS evaluation dataset.

For each cloned repo in examples/repos/:
  1. Tries preferred examples first; auto-discovers others as fallback.
  2. Fills missing Terraform variables with generated sensible values.
  3. Runs `terraform plan -refresh=false` and `terraform show -json`.
  4. Saves base plan JSON  -> dataset/plans/base/<repo>/<example>/base.json
  5. Copies .tf files      -> dataset/examples/<repo>/<example>/

Prerequisites:
    bash examples/clone_repos.sh   # clone repos into examples/repos/

Usage:
    python dataset/select_examples.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT         = Path(__file__).resolve().parents[1]
REPOS_DIR    = ROOT / "examples" / "repos"
DATASET_DIR  = Path(__file__).parent
EXAMPLES_OUT = DATASET_DIR / "examples"
BASE_PLANS   = DATASET_DIR / "plans" / "base"
WORK_DIR     = DATASET_DIR / "_work"

# ---------------------------------------------------------------------------
# Resource types covered by CICS rules (mirrors rules.py type sets)
COST_RELEVANT_TYPES = {
    "aws_instance", "aws_launch_template", "aws_launch_configuration",
    "aws_db_instance", "aws_rds_cluster", "aws_rds_cluster_instance",
    "aws_autoscaling_group", "aws_appautoscaling_target",
    "aws_ebs_volume",
    "aws_nat_gateway",
    "aws_lb", "aws_alb", "aws_elb",
    "aws_cloudfront_distribution", "aws_api_gateway_rest_api",
    "aws_elasticache_cluster", "aws_elasticache_replication_group",
    "aws_sqs_queue",
    "google_compute_instance", "google_compute_instance_template",
    "google_sql_database_instance",
    "google_container_cluster", "google_container_node_pool",
    "google_compute_router_nat",
    "google_compute_forwarding_rule", "google_compute_backend_service",
    "google_redis_instance", "google_pubsub_topic",
}

# ---------------------------------------------------------------------------
# Preferred examples per repo — tried first; auto-discovery fills the rest.
# Set to [] to skip a repo entirely.
PREFERRED_EXAMPLES = {
    "terraform-aws-modules__terraform-aws-ec2-instance":
        ["complete", "spot", "volume-attachment"],
    "terraform-aws-modules__terraform-aws-rds":
        ["complete-postgres", "complete-mysql", "replica-postgres"],
    "terraform-aws-modules__terraform-aws-autoscaling":
        ["complete", "mixed-instance"],
    "terraform-aws-modules__terraform-aws-eks":
        ["eks-managed-node-group", "complete"],
    "terraform-aws-modules__terraform-aws-alb":
        ["complete-alb", "complete-nlb"],
    "terraform-aws-modules__terraform-aws-vpc":
        ["complete-vpc", "simple-vpc"],
    "terraform-aws-modules__terraform-aws-s3-bucket":
        ["complete", "object"],
    "terraform-aws-modules__terraform-aws-iam":
        ["iam-role", "iam-policy"],
    "terraform-aws-modules__terraform-aws-security-group":
        ["complete", "http-80"],
    "terraform-aws-modules__terraform-aws-cloudwatch":
        ["complete"],
    "terraform-google-modules__terraform-google-sql-db":
        ["postgresql-ha", "mysql-private"],
    "terraform-google-modules__terraform-google-kubernetes-engine":
        ["simple_regional", "safer_cluster"],
    "terraform-google-modules__terraform-google-network":
        ["simple_project"],
    "terraform-google-modules__terraform-google-vm":
        ["instance_template", "compute_instance"],
    "terraform-google-modules__terraform-google-project-factory":
        ["simple_project"],
    "terraform-google-modules__terraform-example-foundation":
        [],  # too complex — skip
}

# ---------------------------------------------------------------------------
# Variable name substring -> default value (matched lower-case)
_NAME_DEFAULTS = [
    (["availability_zones", "azs"],
     ["us-east-1a", "us-east-1b"]),
    (["availability_zone"],
     "us-east-1a"),
    (["private_subnets", "public_subnets", "subnet_ids", "subnets"],
     ["subnet-00000000", "subnet-11111111"]),
    (["security_group_ids", "sg_ids"],
     ["sg-00000000"]),
    (["security_group_id", "sg_id"],
     "sg-00000000"),
    (["subnet_id"],
     "subnet-00000000"),
    (["vpc_id"],
     "vpc-00000000"),
    (["cidr_block", "vpc_cidr", "cidr"],
     "10.0.0.0/16"),
    (["region"],
     "us-east-1"),
    (["zone"],
     "us-central1-a"),
    (["instance_type", "machine_type"],
     "t3.micro"),
    (["ami_id", "ami"],
     "ami-00000000"),
    (["key_name", "key_pair"],
     "cics-key"),
    (["master_username", "db_username", "username"],
     "admin"),
    (["master_password", "db_password", "password"],
     "Admin12345!"),
    (["db_name", "database_name", "database"],
     "cicsdb"),
    (["engine_version"],
     "15.4"),
    (["bucket_name", "bucket"],
     "cics-example-bucket"),
    (["account_id"],
     "123456789012"),
    (["project_id", "project"],
     "cics-project"),
    (["cluster_name", "name", "identifier", "label"],
     "cics-example"),
    (["environment", "env", "stage"],
     "dev"),
    (["tags", "labels", "common_tags"],
     {}),
    (["min_size", "min_count", "min_capacity", "min_node"],
     1),
    (["max_size", "max_count", "max_capacity", "max_node"],
     3),
    (["desired_capacity", "initial_node_count"],
     1),
    (["port"],
     5432),
]


def _default_value(name: str, type_str: str) -> object:
    nl = name.lower()
    for patterns, val in _NAME_DEFAULTS:
        if any(p in nl for p in patterns):
            return val
    t = type_str.lower().strip()
    if "list" in t or "set" in t:
        return []
    if "map" in t or "object" in t:
        return {}
    if t == "bool":
        return False
    if t == "number":
        return 1
    return "example"


# ---------------------------------------------------------------------------
def _parse_required_vars(content: str) -> list[dict]:
    """Return [{name, type}] for every variable block that has no default."""
    required, lines, i = [], content.splitlines(), 0
    while i < len(lines):
        m = re.match(r'\s*variable\s+"([^"]+)"', lines[i])
        if m:
            name = m.group(1)
            depth = lines[i].count("{") - lines[i].count("}")
            block, j = [lines[i]], i + 1
            while j < len(lines) and depth > 0:
                depth += lines[j].count("{") - lines[j].count("}")
                block.append(lines[j])
                j += 1
            body = "\n".join(block)
            if "default" not in body:
                tm = re.search(r'type\s*=\s*([^\n#]+)', body)
                required.append({
                    "name": name,
                    "type": tm.group(1).strip() if tm else "any",
                })
            i = j
        else:
            i += 1
    return required


def _fill_variables(work_dir: Path) -> None:
    """Collect all variables.tf files and write a generated .auto.tfvars."""
    required, seen = [], set()
    for vf in work_dir.rglob("variables.tf"):
        for v in _parse_required_vars(vf.read_text(errors="replace")):
            if v["name"] not in seen:
                seen.add(v["name"])
                required.append(v)
    if not required:
        return
    lines = ["# Generated by CICS dataset/select_examples.py\n"]
    for v in required:
        lines.append(f'{v["name"]} = {json.dumps(_default_value(v["name"], v["type"]))}\n')
    (work_dir / "cics_generated.auto.tfvars").write_text("".join(lines))


# ---------------------------------------------------------------------------
def _run_plan(work_dir: Path) -> dict | None:
    """Run terraform plan -refresh=false; return parsed plan JSON or None."""
    env = {**os.environ, "TF_INPUT": "0"}

    def _sh(cmd):
        return subprocess.run(
            cmd, cwd=work_dir, capture_output=True, text=True, env=env
        )

    if not (work_dir / ".terraform").exists():
        r = _sh(["terraform", "init", "-backend=false", "-input=false", "-no-color"])
        if r.returncode != 0:
            print(f"init failed:\n    {r.stderr.strip()[-300:]}")
            return None

    plan_bin = work_dir / "_cics.bin"
    r = _sh([
        "terraform", "plan",
        "-refresh=false", "-lock=false", "-input=false", "-no-color",
        f"-out={plan_bin}",
    ])
    if r.returncode != 0:
        print(f"plan failed:\n    {r.stderr.strip()[-300:]}")
        return None

    r = _sh(["terraform", "show", "-json", str(plan_bin)])
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
def _try_example(repo_name: str, example_name: str, src_dir: Path) -> bool:
    """Copy, fill vars, plan, save base plan and .tf files. Returns True on success."""
    print(f"  {example_name} ...", end=" ", flush=True)

    work = WORK_DIR / repo_name / example_name
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(src_dir, work, symlinks=False)

    _fill_variables(work)
    plan = _run_plan(work)

    if plan is None:
        shutil.rmtree(work, ignore_errors=True)
        return False

    rcs   = plan.get("resource_changes", [])
    types = {rc.get("type") for rc in rcs}
    score = len(types & COST_RELEVANT_TYPES)

    if score == 0:
        print(f"ok but 0 cost-relevant resources ({len(rcs)} total) — skipping")
        shutil.rmtree(work, ignore_errors=True)
        return False

    out_plan = BASE_PLANS / repo_name / example_name / "base.json"
    out_plan.parent.mkdir(parents=True, exist_ok=True)
    out_plan.write_text(json.dumps(plan, indent=2))

    out_tf = EXAMPLES_OUT / repo_name / example_name
    if out_tf.exists():
        shutil.rmtree(out_tf)
    shutil.copytree(work, out_tf, symlinks=False)

    shutil.rmtree(work, ignore_errors=True)
    print(f"saved ({score} cost-relevant type(s), {len(rcs)} resource(s))")
    return True


def _process_repo(repo_name: str) -> int:
    repo_dir = REPOS_DIR / repo_name
    if not repo_dir.exists():
        print(f"  not cloned — run examples/clone_repos.sh")
        return 0

    preferred = PREFERRED_EXAMPLES.get(repo_name)
    if preferred is not None and len(preferred) == 0:
        print(f"  skipped")
        return 0

    examples_root = repo_dir / "examples"
    if not examples_root.exists():
        print(f"  no examples/ directory")
        return 0

    seen       = set(preferred or [])
    candidates = list(preferred or [])
    for d in sorted(examples_root.iterdir()):
        if d.is_dir() and d.name not in seen:
            candidates.append(d.name)

    successes = 0
    for name in candidates:
        src = examples_root / name
        if not src.is_dir():
            continue
        if _try_example(repo_name, name, src):
            successes += 1
        if successes >= 2:
            break

    if successes == 0:
        print(f"  no usable examples found for this repo")
    return successes


def main():
    if not REPOS_DIR.exists() or not any(REPOS_DIR.iterdir()):
        print("examples/repos/ is empty. Run: bash examples/clone_repos.sh")
        sys.exit(1)

    repos = sorted(d for d in REPOS_DIR.iterdir() if d.is_dir())
    print(f"Processing {len(repos)} repo(s) ...\n")

    total = 0
    for repo_dir in repos:
        print(f"[{repo_dir.name}]")
        total += _process_repo(repo_dir.name)
        print()

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)

    print(f"Done. {total} example(s) prepared.")
    print(f"Base plans saved to: {BASE_PLANS}")
    print(f"Next step: python dataset/build_plans.py")


if __name__ == "__main__":
    main()
