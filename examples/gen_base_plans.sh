#!/usr/bin/env bash
# gen_base_plans.sh
#
# Walks every repo in examples/repos/, enters each sub-folder of examples/,
# runs:
#   terraform init  -backend=false -input=false -no-color
#   terraform plan  -refresh=false -lock=false  -input=false -no-color
#   terraform show  -json  > base.json
#
# Output:  dataset/plans/base/<repo>/<example>/base.json
# Usage:   bash examples/gen_base_plans.sh          (from project root)
#      OR  bash gen_base_plans.sh                   (from examples/)

set -uo pipefail

# ── Resolve paths ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -d "$SCRIPT_DIR/repos" ]]; then
    # Running from inside examples/
    REPOS_DIR="$SCRIPT_DIR/repos"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
else
    # Running from project root
    REPOS_DIR="$SCRIPT_DIR/examples/repos"
    PROJECT_ROOT="$SCRIPT_DIR"
fi

BASE_PLANS="$PROJECT_ROOT/dataset/plans/base"

# ── Colors ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()    { echo -e "  ${GREEN}OK${NC}    $*"; }
fail()  { echo -e "  ${RED}FAIL${NC}  $*"; }
skip()  { echo -e "  ${YELLOW}SKIP${NC}  $*"; }

# ── Default values for common required variable names ───────────────────────
# Called with the variable name; prints a Terraform-compatible HCL value.
var_default() {
    local name
    name="$(echo "$1" | tr '[:upper:]' '[:lower:]')"
    if   [[ "$name" == "availability_zones" || "$name" == "azs" ]];
         then echo '["us-east-1a", "us-east-1b"]'
    elif [[ "$name" =~ availability_zone ]];
         then echo '"us-east-1a"'
    elif [[ "$name" =~ private_subnets|public_subnets|subnet_ids ]];
         then echo '["subnet-00000000", "subnet-11111111"]'
    elif [[ "$name" =~ security_group_ids ]];
         then echo '["sg-00000000"]'
    elif [[ "$name" =~ security_group_id|^sg_id$ ]];
         then echo '"sg-00000000"'
    elif [[ "$name" =~ subnet_id ]];
         then echo '"subnet-00000000"'
    elif [[ "$name" =~ vpc_id ]];
         then echo '"vpc-00000000"'
    elif [[ "$name" =~ cidr_block|vpc_cidr|^cidr$ ]];
         then echo '"10.0.0.0/16"'
    elif [[ "$name" == "region" ]];
         then echo '"us-east-1"'
    elif [[ "$name" == "zone" ]];
         then echo '"us-central1-a"'
    elif [[ "$name" =~ instance_type ]];
         then echo '"t3.micro"'
    elif [[ "$name" =~ machine_type ]];
         then echo '"e2-medium"'
    elif [[ "$name" =~ ami_id|^ami$ ]];
         then echo '"ami-00000000"'
    elif [[ "$name" =~ key_name|key_pair ]];
         then echo '"cics-key"'
    elif [[ "$name" =~ username|master_user ]];
         then echo '"admin"'
    elif [[ "$name" =~ password ]];
         then echo '"Admin12345!"'
    elif [[ "$name" =~ db_name|database ]];
         then echo '"cicsdb"'
    elif [[ "$name" =~ engine_version ]];
         then echo '"15.4"'
    elif [[ "$name" =~ bucket ]];
         then echo '"cics-bucket"'
    elif [[ "$name" =~ account_id ]];
         then echo '"123456789012"'
    elif [[ "$name" =~ project_id|^project$ ]];
         then echo '"cics-project"'
    elif [[ "$name" == "name" || "$name" =~ cluster_name|identifier|^label$ ]];
         then echo '"cics-example"'
    elif [[ "$name" =~ environment|^env$|stage ]];
         then echo '"dev"'
    elif [[ "$name" =~ min_size|min_count|min_capacity ]];
         then echo '1'
    elif [[ "$name" =~ max_size|max_count|max_capacity ]];
         then echo '3'
    elif [[ "$name" =~ desired|initial_node ]];
         then echo '1'
    elif [[ "$name" == "port" ]];
         then echo '5432'
    else echo '"example"'
    fi
}

# ── Write cics_generated.auto.tfvars for required (no-default) variables ────
# Uses Python to parse variable blocks (handles nested braces reliably).
write_tfvars() {
    local dir="$1"
    local tfvars="$dir/cics_generated.auto.tfvars"

    local required_vars
    required_vars=$(python3 - "$dir" <<'PYEOF'
import re, sys
from pathlib import Path

d = Path(sys.argv[1])
seen, required = set(), []
for vf in d.rglob("variables.tf"):
    content = vf.read_text(errors="replace")
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r'\s*variable\s+"([^"]+)"', lines[i])
        if m:
            name = m.group(1)
            depth = lines[i].count('{') - lines[i].count('}')
            block, j = [lines[i]], i + 1
            while j < len(lines) and depth > 0:
                depth += lines[j].count('{') - lines[j].count('}')
                block.append(lines[j])
                j += 1
            body = '\n'.join(block)
            if 'default' not in body and name not in seen:
                seen.add(name); required.append(name)
            i = j
        else:
            i += 1
for v in required:
    print(v)
PYEOF
    )

    if [[ -z "$required_vars" ]]; then
        return 0   # nothing to fill
    fi

    {
        echo "# Auto-generated by gen_base_plans.sh — safe to delete"
        while IFS= read -r varname; do
            [[ -n "$varname" ]] && echo "$varname = $(var_default "$varname")"
        done <<< "$required_vars"
    } > "$tfvars"
}

# ── Process one example folder ───────────────────────────────────────────────
run_example() {
    local repo="$1" example="$2" dir="$3"
    local out_dir="$BASE_PLANS/$repo/$example"
    local out_json="$out_dir/base.json"
    local plan_bin="$dir/_cics_plan.bin"
    local log="/tmp/cics_tf_$$.log"

    printf "  %-35s" "$example"

    # Already done?
    if [[ -f "$out_json" ]]; then
        skip "already exists"
        return 0
    fi

    # Fill any required variables
    write_tfvars "$dir"

    # ── terraform init ──
    if [[ ! -d "$dir/.terraform" ]]; then
        if ! terraform -chdir="$dir" init \
                -backend=false -input=false -no-color \
                > "$log" 2>&1; then
            fail "init failed: $(grep -m1 'Error' "$log" | head -c 100)"
            rm -f "$dir/cics_generated.auto.tfvars" "$log"
            return 1
        fi
    fi

    # ── terraform plan ──
    if ! terraform -chdir="$dir" plan \
            -refresh=false -lock=false -input=false -no-color \
            -out="$plan_bin" \
            > "$log" 2>&1; then
        fail "plan failed: $(grep -m1 'Error\|error' "$log" | sed 's/^[[:space:]]*//' | head -c 120)"
        rm -f "$dir/cics_generated.auto.tfvars" "$plan_bin" "$log"
        return 1
    fi

    # ── terraform show -json ──
    mkdir -p "$out_dir"
    if ! terraform -chdir="$dir" show -json "$plan_bin" \
            > "$out_json" 2>"$log"; then
        fail "show failed: $(head -1 "$log")"
        rm -f "$out_json" "$plan_bin" "$dir/cics_generated.auto.tfvars" "$log"
        return 1
    fi

    rm -f "$plan_bin" "$dir/cics_generated.auto.tfvars" "$log"
    ok "saved → $out_json"
    return 0
}

# ── Main ─────────────────────────────────────────────────────────────────────
if [[ ! -d "$REPOS_DIR" ]]; then
    echo "ERROR: repos directory not found at $REPOS_DIR"
    echo "Run first: bash examples/clone_repos.sh"
    exit 1
fi

if ! command -v terraform &>/dev/null; then
    echo "ERROR: 'terraform' not found in PATH"
    exit 1
fi

echo "Terraform: $(terraform version -json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["terraform_version"])' 2>/dev/null || terraform version | head -1)"
echo "Repos dir: $REPOS_DIR"
echo "Output:    $BASE_PLANS"
echo ""

total=0; failed=0; skipped=0

for repo_dir in "$REPOS_DIR"/*/; do
    [[ -d "$repo_dir" ]] || continue
    repo="$(basename "$repo_dir")"
    examples_root="$repo_dir/examples"

    if [[ ! -d "$examples_root" ]]; then
        continue
    fi

    echo "[$repo]"

    for ex_dir in "$examples_root"/*/; do
        [[ -d "$ex_dir" ]] || continue
        example="$(basename "$ex_dir")"

        # Skip if no .tf files at all
        if ! find "$ex_dir" -maxdepth 1 -name "*.tf" | grep -q .; then
            printf "  %-35s" "$example"
            skip "no .tf files"
            skipped=$((skipped + 1))
            continue
        fi

        if run_example "$repo" "$example" "$ex_dir"; then
            total=$((total + 1))
        else
            failed=$((failed + 1))
        fi
    done
    echo ""
done

echo "--------------------------------------------"
echo "Saved:   $total"
echo "Failed:  $failed"
echo "Skipped: $skipped"
echo "Output:  $BASE_PLANS"
echo ""
if [[ $total -gt 0 ]]; then
    echo "Next step: python dataset/build_plans.py"
fi
