# CICS /kɪks/ → Cost-Impact Change Signals for Terraform

> **FinOps-Aware IaC Review for DevOps**  
> Detect and explain cost-impacting Terraform changes at pull-request time - no cloud credentials required beyond what Terraform already uses.

---

## What is CICS?

When a developer opens a pull request that upgrades an RDS instance class, raises
an auto-scaling minimum, or enables Multi-AZ, the cost impact is invisible to
reviewers. CICS solves this by analysing the **Terraform plan JSON**
(`terraform show -json`) and emitting structured **cost-impact signals** - each
with a category, direction (increase / decrease / uncertain), severity, and an
AI-generated natural-language explanation.

CICS is the artefact accompanying the research paper:

> **"FinOps-Aware IaC Review for DevOps: Plan-Aware Detection of Cost-Impacting
> Terraform Changes with Explainable Feedback"**  
> Usman Sadiq - NUST EME (MS-SE), 2026

---

## Key Features

| Feature | Detail |
|---|---|
| **Plan-aware** | Reads `terraform show -json` - catches replace-vs-update semantics that `.tf` diffs miss |
| **13 rules** | Compute sizing, scaling bounds, storage, availability/replication, networking, managed services |
| **Direction classification** | increase / decrease / uncertain (not just "something changed") |
| **AI explanations** | Evidence-bounded Claude explanations - no hallucinated prices |
| **Zero false positives** | Tag changes, IAM updates, SG rule edits are correctly ignored |
| **Provider-agnostic** | AWS and GCP resource types covered out of the box |
| **CI-ready** | Outputs JSON/JSONL; trivial to post as a PR comment |

---

## Quick Start

### 1. Install

```bash
pip install cics
```

This installs the `cics` command-line tool and all dependencies automatically.

### 2. Run against your Terraform plan

```bash
# Generate plan JSON (standard Terraform commands)
terraform init
terraform plan -out=plan.tfplan
terraform show -json plan.tfplan > plan.json

# Run CICS
cics --plan plan.json
```

### 3. With AI explanations

```bash
export ANTHROPIC_API_KEY=sk-ant-...
cics --plan plan.json --explain
```

### 4. Save findings to JSON

```bash
cics --plan plan.json --explain --out findings.json
```

---

## CI/CD Integration - PR Review

CICS can post cost-impact findings as a PR comment automatically on every push.
Two ready-to-use example pipelines are provided in the `examples/` folder -
one for GitHub Actions and one for Bitbucket Pipelines. Both do the same thing:
run `terraform plan`, analyse it with CICS, and post a structured comment with
severity icons, direction arrows, evidence fields, and AI explanations. On
follow-up pushes the comment is updated in place rather than duplicated.

> **Note on credentials and before-vs-after comparison**
> CICS compares the `before` and `after` values in the Terraform plan to detect
> what changed (e.g. `instance_type` t3.micro -> m5.large). The `before` values
> come from your Terraform state. Without cloud credentials, Terraform cannot
> reach your remote backend, so `before` is always null - CICS will still flag
> new expensive resources being added, but it will not show what an existing
> resource looked like before the change. For full change detection on existing
> infrastructure, supply credentials and remove `-backend=false` from the
> `terraform init` call inside the pipeline file.

---

### GitHub Actions

```bash
# In your repository:
mkdir -p .github/workflows
cp examples/cics-pr-review.yml .github/workflows/
```

Add your Anthropic API key as a repository secret:

1. Go to your repo on GitHub
2. **Settings > Secrets and variables > Actions > New repository secret**
3. Name: `ANTHROPIC_API_KEY` - Value: your key from https://console.anthropic.com/

See [`examples/cics-pr-review.yml`](examples/cics-pr-review.yml) for the full
workflow with inline notes on AWS/GCP credential setup.

---

### Bitbucket Pipelines

```bash
# In your repository:
cp examples/cics-pr-review-bitbucket.yml bitbucket-pipelines.yml
# (or merge the pull-requests: section into your existing bitbucket-pipelines.yml)
```

Bitbucket requires an **App Password** to post PR comments (there is no
auto-provided token like GitHub's `GITHUB_TOKEN`):

1. Go to **Account settings > App passwords > Create app password**
2. Enable: Repositories: Read - Pull requests: Read, Write
3. Add two repository variables under **Repository settings > Pipelines >
   Repository variables**:
    - `BB_USER` - your Bitbucket username
    - `BB_APP_PASSWORD` - the app password you just created (mark Secured)

Then add your Anthropic API key the same way:

- `ANTHROPIC_API_KEY` - your key from https://console.anthropic.com/ (mark Secured)

See [`examples/cics-pr-review-bitbucket.yml`](examples/cics-pr-review-bitbucket.yml)
for the full pipeline with inline notes on AWS/GCP credential setup.

---

## Running the Research Evaluation

Reproduces all results from the paper (Section 5–7) without any cloud account:

```bash
git clone https://github.com/usmansadiq786/cics.git
cd cics/fin-aware

# Build the 35 curated plan JSON files + run evaluation
python run_all.py

# Output (actual results):
# CICS   - Precision: 100.0%  Recall: 100.0%  F1: 100.0%  Dir. Acc: 100.0%
# Naive  - Precision:  85.7%  Recall: 100.0%  F1:  92.3%  Dir. Acc:  23.3%
```

Results are saved to `results/eval_results.json`.

---

## Dataset

The evaluation dataset lives in `dataset/plans/` - 35 Terraform plan JSON files
organised by source repository and example:

```
dataset/plans/
├── terraform-aws-modules__terraform-aws-ec2-instance/
│   ├── complete/            S001 (t3.micro->m5.large), S002 (downsize), …
│   └── session-manager/     S003 (launch template upsize)
├── terraform-aws-modules__terraform-aws-rds/
│   ├── complete-postgres/   S004, S013, S018, S019, S020, S028, S029
│   ├── replica-postgres/    S005, S014
│   ├── complete-mysql/      S027
│   └── cross-region-…/      S021
├── terraform-aws-modules__terraform-aws-autoscaling/
│   └── complete/            S007, S008, S009
├── terraform-aws-modules__terraform-aws-alb/
│   ├── complete-alb/        S024, S030
│   └── complete-nlb/        S025
├── terraform-aws-modules__terraform-aws-vpc/
│   └── complete-vpc/        S023
├── terraform-aws-modules__terraform-aws-eks/
│   └── eks-managed-node-group/  S010, S011, S012
├── terraform-google-modules__terraform-google-sql-db/
│   └── postgresql-ha/       S016, S022
└── … (S031–S035 are false-positive test cases)
```

**Scenarios:** 30 cost-impacting + 5 non-cost-impacting (FP tests)  
**Source repos:** 16 (10 AWS, 6 GCP)  
**No cloud credentials needed** - all plan JSONs are synthetically generated from
real resource types and attribute names; see `dataset/scenarios.py` for all
definitions and ground-truth labels.

To regenerate the plan JSON files from scratch:

```bash
python dataset/build_plans.py
```

---

## Rule Catalog

| ID | Category | Trigger | Direction |
|---|---|---|---|
| C1 | Compute sizing | instance type upsize (update/replace) | ↑ |
| C2 | Compute sizing | instance type downsize (update/replace) | ↓ |
| S1 | Scaling bounds | min replicas/size increases | ↑ |
| S2 | Scaling bounds | max replicas/size increases | ↑ |
| S3 | Scaling bounds | any scaling bound decreases | ↓ |
| ST1 | Storage capacity | volume/allocated storage size changes | ↑↓ |
| ST2 | Storage tier | volume_type / storage_type changes | ↑↓/~ |
| A1 | Availability | multi-AZ or replicas enabled/increased | ↑ |
| A2 | Availability | multi-AZ or replicas disabled/decreased | ↓ |
| N1 | Networking | NAT/egress gateway created | ↑ |
| N2 | Load balancing | load balancer created | ↑ |
| N3 | Data transfer | CDN / traffic-metered resource created | ~ |
| M1 | Managed service | DB / cache / queue created | ↑ |
| M2 | Replacement spike | managed DB or LB resource replaced | ↑+risk |

`~` = uncertain (cost depends on runtime usage not visible in plan)

---

## Project Structure

```
fin-aware/
├── cics/
│   ├── run.py            # CLI entry point (cics command)
│   ├── rules.py          # 13-rule engine with instance-type scoring
│   ├── extractor.py      # Terraform plan JSON parser
│   └── explainer.py      # Evidence-bounded Claude API explainer
├── dataset/
│   ├── scenarios.py      # All 35 scenario definitions + ground truth
│   ├── build_plans.py    # Generates plan JSON files from scenarios
│   └── plans/            # 35 plan JSON files (auto-generated)
├── eval/
│   └── evaluate.py       # Precision / Recall / F1 / Direction Accuracy
├── examples/
│   ├── cics-pr-review.yml            # GitHub Actions PR review workflow (copy to your repo)
│   ├── cics-pr-review-bitbucket.yml  # Bitbucket Pipelines PR review pipeline (copy to your repo)
│   ├── clone_repos.sh                # Clone/update all 16 sample repos
│   └── sample_repos.txt              # 16 public Terraform repos used in the study
├── results/
│   └── eval_results.json # Saved evaluation output
├── paper/
│   ├── R6_main.tex       # Final research paper (LaTeX, twocolumn)
│   └── refs.bib          # BibTeX references
├── pyproject.toml        # Package metadata and CLI entry point
├── run_all.py            # One-command pipeline runner
└── requirements.txt
```

---

## Citation

If you use CICS or this dataset in your research, please cite:

```bibtex
@misc{sadiq2026cics,
  author       = {Sadiq, Usman},
  title        = {{CICS}: Cost-Impact Change Signals for Terraform},
  year         = {2026},
  howpublished = {\url{https://github.com/usmansadiq786/cics}},
  note         = {NUST EME MS-SE Research Artefact}
}
```

---

## License

This project is released under the **MIT License** - see [LICENSE](LICENSE) for
details. You are free to use, modify, and distribute CICS in academic or
commercial contexts. Attribution is appreciated but not required.

---

## Acknowledgements

Supervised by Dr. Farooque Azam and Muhammad Waseem Anwar, NUST EME College of
Engineering. Dataset derived from public repositories maintained by
[terraform-aws-modules](https://github.com/terraform-aws-modules) and
[terraform-google-modules](https://github.com/terraform-google-modules).
