"""
35 curated test scenarios derived from 16 public Terraform module repositories.
30 cost-impacting + 5 non-cost-impacting (false-positive test cases).

Each scenario maps to a plan JSON file that build_plans.py writes under
  dataset/plans/<repo_folder>/<example_folder>/<scenario_id>.json

ground_truth fields
-------------------
is_cost_impacting : bool   -- whether the change has a real cost impact
direction         : str    -- "increase" | "decrease" | "uncertain" | None
category          : str    -- CICS rule category
expected_rule_ids : list   -- which rule IDs should fire

repo field
----------
The "repo" key in each scenario matches the folder name produced by
examples/clone_repos.sh (GitHub org/name with "/" replaced by "__").
SOURCE_REPOS below maps each folder name to its GitHub URL.
Clone the source repos to browse the real .tf files each scenario was
derived from:
    bash examples/clone_repos.sh     # clones into examples/repos/
"""

from pathlib import Path


# Maps scenario "repo" folder names to their GitHub source URLs.
# Built from examples/sample_repos.txt - that file is the single source of
# truth. Add a repo there and it appears here automatically.
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

SCENARIOS = [

    # ══════════════════════════════════════════════════════════════════════
    # COMPUTE SIZING  (C1 / C2)  – 6 scenarios
    # ══════════════════════════════════════════════════════════════════════
    {
        "id": "S001",
        "repo": "terraform-aws-modules__terraform-aws-ec2-instance",
        "example": "complete",
        "description": "EC2 instance_type upsize: t3.micro -> m5.large",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Compute sizing",
            "expected_rule_ids": ["C1"],
        },
        "resource_changes": [{
            "address": "module.ec2_complete.aws_instance.this[0]",
            "type": "aws_instance",
            "change": {
                "actions": ["update"],
                "before": {"instance_type": "t3.micro", "ami": "ami-0abc1234",
                           "tags": {"Name": "ec2-complete", "Env": "prod"}},
                "after": {"instance_type": "m5.large", "ami": "ami-0abc1234",
                          "tags": {"Name": "ec2-complete", "Env": "prod"}},
            },
        }],
    },
    {
        "id": "S002",
        "repo": "terraform-aws-modules__terraform-aws-ec2-instance",
        "example": "complete",
        "description": "EC2 instance_type downsize: m5.xlarge -> t3.small",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "decrease",
            "category": "Compute sizing",
            "expected_rule_ids": ["C2"],
        },
        "resource_changes": [{
            "address": "module.ec2_complete.aws_instance.this[0]",
            "type": "aws_instance",
            "change": {
                "actions": ["update"],
                "before": {"instance_type": "m5.xlarge", "ami": "ami-0abc1234"},
                "after": {"instance_type": "t3.small", "ami": "ami-0abc1234"},
            },
        }],
    },
    {
        "id": "S003",
        "repo": "terraform-aws-modules__terraform-aws-ec2-instance",
        "example": "session-manager",
        "description": "EC2 launch template instance_type upsize: t3.medium -> m5.2xlarge",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Compute sizing",
            "expected_rule_ids": ["C1"],
        },
        "resource_changes": [{
            "address": "module.ec2_session.aws_launch_template.this[0]",
            "type": "aws_launch_template",
            "change": {
                "actions": ["update"],
                "before": {"instance_type": "t3.medium"},
                "after": {"instance_type": "m5.2xlarge"},
            },
        }],
    },
    {
        "id": "S004",
        "repo": "terraform-aws-modules__terraform-aws-rds",
        "example": "complete-postgres",
        "description": "RDS instance_class upsize: db.t4g.large -> db.r5.4xlarge",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Compute sizing",
            "expected_rule_ids": ["C1"],
        },
        "resource_changes": [{
            "address": "module.db.aws_db_instance.this[0]",
            "type": "aws_db_instance",
            "change": {
                "actions": ["update"],
                "before": {"instance_class": "db.t4g.large", "engine": "postgres",
                           "identifier": "complete-postgresql"},
                "after": {"instance_class": "db.r5.4xlarge", "engine": "postgres",
                          "identifier": "complete-postgresql"},
            },
        }],
    },
    {
        "id": "S005",
        "repo": "terraform-aws-modules__terraform-aws-rds",
        "example": "replica-postgres",
        "description": "RDS instance_class downsize: db.r5.large -> db.t4g.micro",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "decrease",
            "category": "Compute sizing",
            "expected_rule_ids": ["C2"],
        },
        "resource_changes": [{
            "address": "module.db.aws_db_instance.this[0]",
            "type": "aws_db_instance",
            "change": {
                "actions": ["update"],
                "before": {"instance_class": "db.r5.large", "engine": "postgres"},
                "after": {"instance_class": "db.t4g.micro", "engine": "postgres"},
            },
        }],
    },
    {
        "id": "S006",
        "repo": "terraform-aws-modules__terraform-aws-ec2-instance",
        "example": "complete",
        "description": "EC2 same-family scale-up: c5.large -> c5.4xlarge",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Compute sizing",
            "expected_rule_ids": ["C1"],
        },
        "resource_changes": [{
            "address": "module.ec2_spot.aws_instance.this[0]",
            "type": "aws_instance",
            "change": {
                "actions": ["update"],
                "before": {"instance_type": "c5.large"},
                "after": {"instance_type": "c5.4xlarge"},
            },
        }],
    },

    # ══════════════════════════════════════════════════════════════════════
    # SCALING BOUNDS  (S1 / S2 / S3)  – 6 scenarios
    # ══════════════════════════════════════════════════════════════════════
    {
        "id": "S007",
        "repo": "terraform-aws-modules__terraform-aws-autoscaling",
        "example": "complete",
        "description": "ASG min_size increase: 1 -> 3",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Scaling bounds",
            "expected_rule_ids": ["S1"],
        },
        "resource_changes": [{
            "address": "module.complete.aws_autoscaling_group.this[0]",
            "type": "aws_autoscaling_group",
            "change": {
                "actions": ["update"],
                "before": {"min_size": 1, "max_size": 5, "desired_capacity": 1},
                "after": {"min_size": 3, "max_size": 5, "desired_capacity": 3},
            },
        }],
    },
    {
        "id": "S008",
        "repo": "terraform-aws-modules__terraform-aws-autoscaling",
        "example": "complete",
        "description": "ASG max_size increase: 5 -> 20",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Scaling bounds",
            "expected_rule_ids": ["S2"],
        },
        "resource_changes": [{
            "address": "module.complete.aws_autoscaling_group.this[0]",
            "type": "aws_autoscaling_group",
            "change": {
                "actions": ["update"],
                "before": {"min_size": 1, "max_size": 5, "desired_capacity": 2},
                "after": {"min_size": 1, "max_size": 20, "desired_capacity": 2},
            },
        }],
    },
    {
        "id": "S009",
        "repo": "terraform-aws-modules__terraform-aws-autoscaling",
        "example": "complete",
        "description": "ASG scaling bounds decrease: min 5->1, max 10->3",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "decrease",
            "category": "Scaling bounds",
            "expected_rule_ids": ["S3"],
        },
        "resource_changes": [{
            "address": "module.complete.aws_autoscaling_group.this[0]",
            "type": "aws_autoscaling_group",
            "change": {
                "actions": ["update"],
                "before": {"min_size": 5, "max_size": 10, "desired_capacity": 5},
                "after": {"min_size": 1, "max_size": 3, "desired_capacity": 1},
            },
        }],
    },
    {
        "id": "S010",
        "repo": "terraform-aws-modules__terraform-aws-eks",
        "example": "eks-managed-node-group",
        "description": "App autoscaling min_capacity increase: 1 -> 4",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Scaling bounds",
            "expected_rule_ids": ["S1"],
        },
        "resource_changes": [{
            "address": "aws_appautoscaling_target.eks_nodes",
            "type": "aws_appautoscaling_target",
            "change": {
                "actions": ["update"],
                "before": {"min_capacity": 1, "max_capacity": 10},
                "after": {"min_capacity": 4, "max_capacity": 10},
            },
        }],
    },
    {
        "id": "S011",
        "repo": "terraform-aws-modules__terraform-aws-eks",
        "example": "eks-managed-node-group",
        "description": "App autoscaling max_capacity increase: 10 -> 50",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Scaling bounds",
            "expected_rule_ids": ["S2"],
        },
        "resource_changes": [{
            "address": "aws_appautoscaling_target.eks_nodes",
            "type": "aws_appautoscaling_target",
            "change": {
                "actions": ["update"],
                "before": {"min_capacity": 2, "max_capacity": 10},
                "after": {"min_capacity": 2, "max_capacity": 50},
            },
        }],
    },
    {
        "id": "S012",
        "repo": "terraform-aws-modules__terraform-aws-eks",
        "example": "eks-managed-node-group",
        "description": "App autoscaling min/max decrease: 5/20 -> 1/5",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "decrease",
            "category": "Scaling bounds",
            "expected_rule_ids": ["S3"],
        },
        "resource_changes": [{
            "address": "aws_appautoscaling_target.eks_nodes",
            "type": "aws_appautoscaling_target",
            "change": {
                "actions": ["update"],
                "before": {"min_capacity": 5, "max_capacity": 20},
                "after": {"min_capacity": 1, "max_capacity": 5},
            },
        }],
    },

    # ══════════════════════════════════════════════════════════════════════
    # STORAGE CAPACITY  (ST1)  + STORAGE TIER  (ST2)  – 6 scenarios
    # ══════════════════════════════════════════════════════════════════════
    {
        "id": "S013",
        "repo": "terraform-aws-modules__terraform-aws-rds",
        "example": "complete-postgres",
        "description": "RDS allocated_storage increase: 20 GB -> 200 GB",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Storage capacity",
            "expected_rule_ids": ["ST1"],
        },
        "resource_changes": [{
            "address": "module.db.aws_db_instance.this[0]",
            "type": "aws_db_instance",
            "change": {
                "actions": ["update"],
                "before": {"allocated_storage": 20, "instance_class": "db.t4g.large"},
                "after": {"allocated_storage": 200, "instance_class": "db.t4g.large"},
            },
        }],
    },
    {
        "id": "S014",
        "repo": "terraform-aws-modules__terraform-aws-rds",
        "example": "replica-postgres",
        "description": "RDS allocated_storage decrease: 100 GB -> 50 GB",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "decrease",
            "category": "Storage capacity",
            "expected_rule_ids": ["ST1"],
        },
        "resource_changes": [{
            "address": "module.db.aws_db_instance.this[0]",
            "type": "aws_db_instance",
            "change": {
                "actions": ["update"],
                "before": {"allocated_storage": 100, "instance_class": "db.r5.large"},
                "after": {"allocated_storage": 50, "instance_class": "db.r5.large"},
            },
        }],
    },
    {
        "id": "S015",
        "repo": "terraform-aws-modules__terraform-aws-ec2-instance",
        "example": "complete",
        "description": "EBS volume_size increase: 50 GB -> 200 GB",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Storage capacity",
            "expected_rule_ids": ["ST1"],
        },
        "resource_changes": [{
            "address": "aws_ebs_volume.data",
            "type": "aws_ebs_volume",
            "change": {
                "actions": ["update"],
                "before": {"volume_size": 50, "volume_type": "gp3"},
                "after": {"volume_size": 200, "volume_type": "gp3"},
            },
        }],
    },
    {
        "id": "S016",
        "repo": "terraform-google-modules__terraform-google-sql-db",
        "example": "postgresql-ha",
        "description": "GCP SQL disk_size increase: 10 GB -> 100 GB",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Storage capacity",
            "expected_rule_ids": ["ST1"],
        },
        "resource_changes": [{
            "address": "module.sql.google_sql_database_instance.master",
            "type": "google_sql_database_instance",
            "change": {
                "actions": ["update"],
                "before": {"disk_size": 10, "database_version": "POSTGRES_15"},
                "after": {"disk_size": 100, "database_version": "POSTGRES_15"},
            },
        }],
    },
    {
        "id": "S017",
        "repo": "terraform-aws-modules__terraform-aws-ec2-instance",
        "example": "complete",
        "description": "EBS volume_type tier upgrade: gp2 -> io1",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Storage tier",
            "expected_rule_ids": ["ST2"],
        },
        "resource_changes": [{
            "address": "aws_ebs_volume.data",
            "type": "aws_ebs_volume",
            "change": {
                "actions": ["update"],
                "before": {"volume_size": 100, "volume_type": "gp2"},
                "after": {"volume_size": 100, "volume_type": "io1"},
            },
        }],
    },
    {
        "id": "S018",
        "repo": "terraform-aws-modules__terraform-aws-rds",
        "example": "complete-postgres",
        "description": "RDS storage_type upgrade: gp2 -> io1",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Storage tier",
            "expected_rule_ids": ["ST2"],
        },
        "resource_changes": [{
            "address": "module.db.aws_db_instance.this[0]",
            "type": "aws_db_instance",
            "change": {
                "actions": ["update"],
                "before": {"allocated_storage": 100, "storage_type": "gp2"},
                "after": {"allocated_storage": 100, "storage_type": "io1"},
            },
        }],
    },

    # ══════════════════════════════════════════════════════════════════════
    # AVAILABILITY / REPLICATION  (A1 / A2)  – 4 scenarios
    # ══════════════════════════════════════════════════════════════════════
    {
        "id": "S019",
        "repo": "terraform-aws-modules__terraform-aws-rds",
        "example": "complete-postgres",
        "description": "RDS multi_az enable: false -> true",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Availability/replication",
            "expected_rule_ids": ["A1"],
        },
        "resource_changes": [{
            "address": "module.db.aws_db_instance.this[0]",
            "type": "aws_db_instance",
            "change": {
                "actions": ["update"],
                "before": {"multi_az": False, "instance_class": "db.t4g.large"},
                "after": {"multi_az": True, "instance_class": "db.t4g.large"},
            },
        }],
    },
    {
        "id": "S020",
        "repo": "terraform-aws-modules__terraform-aws-rds",
        "example": "complete-postgres",
        "description": "RDS multi_az disable: true -> false",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "decrease",
            "category": "Availability/replication",
            "expected_rule_ids": ["A2"],
        },
        "resource_changes": [{
            "address": "module.db.aws_db_instance.this[0]",
            "type": "aws_db_instance",
            "change": {
                "actions": ["update"],
                "before": {"multi_az": True, "instance_class": "db.r5.large"},
                "after": {"multi_az": False, "instance_class": "db.r5.large"},
            },
        }],
    },
    {
        "id": "S021",
        "repo": "terraform-aws-modules__terraform-aws-rds",
        "example": "cross-region-replica-postgres",
        "description": "RDS Aurora replica_count increase: 1 -> 3",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Availability/replication",
            "expected_rule_ids": ["A1"],
        },
        "resource_changes": [{
            "address": "module.aurora.aws_rds_cluster.this[0]",
            "type": "aws_rds_cluster",
            "change": {
                "actions": ["update"],
                "before": {"replica_count": 1},
                "after": {"replica_count": 3},
            },
        }],
    },
    {
        "id": "S022",
        "repo": "terraform-google-modules__terraform-google-sql-db",
        "example": "postgresql-ha",
        "description": "GCP SQL availability_type: ZONAL -> REGIONAL",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Availability/replication",
            "expected_rule_ids": ["A1"],
        },
        "resource_changes": [{
            "address": "module.sql.google_sql_database_instance.master",
            "type": "google_sql_database_instance",
            "change": {
                "actions": ["update"],
                "before": {"availability_type": "ZONAL"},
                "after": {"availability_type": "REGIONAL"},
            },
        }],
    },

    # ══════════════════════════════════════════════════════════════════════
    # NETWORKING  (N1 / N2 / N3)  – 4 scenarios
    # ══════════════════════════════════════════════════════════════════════
    {
        "id": "S023",
        "repo": "terraform-aws-modules__terraform-aws-vpc",
        "example": "complete-vpc",
        "description": "NAT gateway created",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Networking gateway",
            "expected_rule_ids": ["N1"],
        },
        "resource_changes": [{
            "address": "module.vpc.aws_nat_gateway.this[0]",
            "type": "aws_nat_gateway",
            "change": {
                "actions": ["create"],
                "before": None,
                "after": {"subnet_id": "subnet-abc", "allocation_id": "eipalloc-xyz"},
            },
        }],
    },
    {
        "id": "S024",
        "repo": "terraform-aws-modules__terraform-aws-alb",
        "example": "complete-alb",
        "description": "Application Load Balancer created",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Load balancing",
            "expected_rule_ids": ["N2"],
        },
        "resource_changes": [{
            "address": "module.alb.aws_lb.this[0]",
            "type": "aws_lb",
            "change": {
                "actions": ["create"],
                "before": None,
                "after": {"name": "complete-alb", "load_balancer_type": "application",
                          "internal": False},
            },
        }],
    },
    {
        "id": "S025",
        "repo": "terraform-aws-modules__terraform-aws-alb",
        "example": "complete-nlb",
        "description": "Network Load Balancer created",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Load balancing",
            "expected_rule_ids": ["N2"],
        },
        "resource_changes": [{
            "address": "module.nlb.aws_lb.this[0]",
            "type": "aws_lb",
            "change": {
                "actions": ["create"],
                "before": None,
                "after": {"name": "complete-nlb", "load_balancer_type": "network",
                          "internal": False},
            },
        }],
    },
    {
        "id": "S026",
        "repo": "terraform-aws-modules__terraform-aws-cloudwatch",
        "example": "complete",
        "description": "CloudFront distribution created (uncertain – traffic-priced)",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "uncertain",
            "category": "Data transfer driver",
            "expected_rule_ids": ["N3"],
        },
        "resource_changes": [{
            "address": "aws_cloudfront_distribution.s3_distribution",
            "type": "aws_cloudfront_distribution",
            "change": {
                "actions": ["create"],
                "before": None,
                "after": {"enabled": True, "comment": "static site CDN"},
            },
        }],
    },

    # ══════════════════════════════════════════════════════════════════════
    # MANAGED SERVICES  (M1 / M2)  – 4 scenarios
    # ══════════════════════════════════════════════════════════════════════
    {
        "id": "S027",
        "repo": "terraform-aws-modules__terraform-aws-rds",
        "example": "complete-mysql",
        "description": "RDS MySQL instance created (M1)",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Managed service intro",
            "expected_rule_ids": ["M1"],
        },
        "resource_changes": [{
            "address": "module.db.aws_db_instance.this[0]",
            "type": "aws_db_instance",
            "change": {
                "actions": ["create"],
                "before": None,
                "after": {"engine": "mysql", "instance_class": "db.t4g.large",
                          "allocated_storage": 20, "identifier": "complete-mysql"},
            },
        }],
    },
    {
        "id": "S028",
        "repo": "terraform-aws-modules__terraform-aws-rds",
        "example": "complete-postgres",
        "description": "RDS Aurora cluster created (M1)",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Managed service intro",
            "expected_rule_ids": ["M1"],
        },
        "resource_changes": [{
            "address": "module.aurora.aws_rds_cluster.this[0]",
            "type": "aws_rds_cluster",
            "change": {
                "actions": ["create"],
                "before": None,
                "after": {"engine": "aurora-postgresql", "engine_version": "15.4",
                          "cluster_identifier": "aurora-cluster"},
            },
        }],
    },
    {
        "id": "S029",
        "repo": "terraform-aws-modules__terraform-aws-rds",
        "example": "complete-postgres",
        "description": "RDS instance replaced (major engine upgrade, M2)",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Replacement spike",
            "expected_rule_ids": ["M2"],
        },
        "resource_changes": [{
            "address": "module.db.aws_db_instance.this[0]",
            "type": "aws_db_instance",
            "change": {
                "actions": ["delete", "create"],
                "before": {"engine": "postgres", "engine_version": "14",
                           "instance_class": "db.t4g.large", "allocated_storage": 20},
                "after": {"engine": "postgres", "engine_version": "16",
                          "instance_class": "db.t4g.large", "allocated_storage": 20},
            },
        }],
    },
    {
        "id": "S030",
        "repo": "terraform-aws-modules__terraform-aws-alb",
        "example": "complete-alb",
        "description": "ALB replaced due to scheme change (M2)",
        "ground_truth": {
            "is_cost_impacting": True,
            "direction": "increase",
            "category": "Replacement spike",
            "expected_rule_ids": ["M2"],
        },
        "resource_changes": [{
            "address": "module.alb.aws_lb.this[0]",
            "type": "aws_lb",
            "change": {
                "actions": ["delete", "create"],
                "before": {"name": "prod-alb", "internal": False,
                           "load_balancer_type": "application"},
                "after": {"name": "prod-alb", "internal": True,
                          "load_balancer_type": "application"},
            },
        }],
    },

    # ══════════════════════════════════════════════════════════════════════
    # NON-COST-IMPACTING  (false-positive test cases)  – 5 scenarios
    # ══════════════════════════════════════════════════════════════════════
    {
        "id": "S031",
        "repo": "terraform-aws-modules__terraform-aws-ec2-instance",
        "example": "complete",
        "description": "EC2 tags-only update – no cost impact",
        "ground_truth": {
            "is_cost_impacting": False,
            "direction": None,
            "category": None,
            "expected_rule_ids": [],
        },
        "resource_changes": [{
            "address": "module.ec2_complete.aws_instance.this[0]",
            "type": "aws_instance",
            "change": {
                "actions": ["update"],
                "before": {"instance_type": "t3.micro", "ami": "ami-0abc1234",
                           "tags": {"Name": "old-name", "Env": "prod"}},
                "after": {"instance_type": "t3.micro", "ami": "ami-0abc1234",
                          "tags": {"Name": "new-name", "Env": "staging"}},
            },
        }],
    },
    {
        "id": "S032",
        "repo": "terraform-aws-modules__terraform-aws-s3-bucket",
        "example": "complete",
        "description": "S3 bucket lifecycle rule update – no cost impact",
        "ground_truth": {
            "is_cost_impacting": False,
            "direction": None,
            "category": None,
            "expected_rule_ids": [],
        },
        "resource_changes": [{
            "address": "module.s3_bucket.aws_s3_bucket.this[0]",
            "type": "aws_s3_bucket",
            "change": {
                "actions": ["update"],
                "before": {"bucket": "my-app-bucket",
                           "versioning": [{"enabled": False}]},
                "after": {"bucket": "my-app-bucket",
                          "versioning": [{"enabled": True}]},
            },
        }],
    },
    {
        "id": "S033",
        "repo": "terraform-aws-modules__terraform-aws-iam",
        "example": "iam-role",
        "description": "IAM role assume_role_policy update – no cost impact",
        "ground_truth": {
            "is_cost_impacting": False,
            "direction": None,
            "category": None,
            "expected_rule_ids": [],
        },
        "resource_changes": [{
            "address": "module.iam_role.aws_iam_role.this[0]",
            "type": "aws_iam_role",
            "change": {
                "actions": ["update"],
                "before": {"assume_role_policy": '{"Version":"2012-10-17"}',
                           "name": "my-role"},
                "after": {"assume_role_policy": '{"Version":"2012-10-17","Statement":[]}',
                          "name": "my-role"},
            },
        }],
    },
    {
        "id": "S034",
        "repo": "terraform-aws-modules__terraform-aws-security-group",
        "example": "complete",
        "description": "Security group ingress rule port change – no cost impact",
        "ground_truth": {
            "is_cost_impacting": False,
            "direction": None,
            "category": None,
            "expected_rule_ids": [],
        },
        "resource_changes": [{
            "address": "module.sg.aws_security_group_rule.ingress_rules[0]",
            "type": "aws_security_group_rule",
            "change": {
                "actions": ["update"],
                "before": {"from_port": 80, "to_port": 80, "protocol": "tcp",
                           "type": "ingress"},
                "after": {"from_port": 443, "to_port": 443, "protocol": "tcp",
                          "type": "ingress"},
            },
        }],
    },
    {
        "id": "S035",
        "repo": "terraform-aws-modules__terraform-aws-ec2-instance",
        "example": "complete",
        "description": "EC2 detailed monitoring toggle – no cost impact",
        "ground_truth": {
            "is_cost_impacting": False,
            "direction": None,
            "category": None,
            "expected_rule_ids": [],
        },
        "resource_changes": [{
            "address": "module.ec2_complete.aws_instance.this[0]",
            "type": "aws_instance",
            "change": {
                "actions": ["update"],
                "before": {"instance_type": "t3.micro", "monitoring": False,
                           "disable_api_termination": False},
                "after": {"instance_type": "t3.micro", "monitoring": True,
                          "disable_api_termination": False},
            },
        }],
    },
]
