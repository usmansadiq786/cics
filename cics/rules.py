"""
CICS Rule Engine – all 13 rules from the R4 catalog.
Each rule emits a Finding with: rule_id, category, direction, severity, evidence.
"""

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    rule_id: str
    category: str
    direction: str  # "increase" | "decrease" | "uncertain"
    severity: str  # "low" | "medium" | "high"
    resource_address: str
    resource_type: str
    actions: list
    evidence: dict
    explanation: Optional[str] = None

    def to_dict(self):
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "direction": self.direction,
            "severity": self.severity,
            "resource_address": self.resource_address,
            "resource_type": self.resource_type,
            "actions": self.actions,
            "evidence": self.evidence,
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Instance-type comparison helpers
# ---------------------------------------------------------------------------

_EC2_SIZE_ORDER = {
    "nano": 0, "micro": 1, "small": 2, "medium": 3, "large": 4,
    "xlarge": 5, "2xlarge": 6, "3xlarge": 7, "4xlarge": 8,
    "6xlarge": 9, "8xlarge": 10, "9xlarge": 10, "10xlarge": 11,
    "12xlarge": 12, "16xlarge": 13, "18xlarge": 14, "24xlarge": 15,
    "32xlarge": 16, "48xlarge": 17, "metal": 18,
}

_EC2_FAMILY_TIER = {
    # burstable
    "t2": 1, "t3": 2, "t3a": 2, "t4g": 2,
    # general purpose
    "m4": 5, "m5": 6, "m5a": 6, "m5n": 6, "m5d": 6,
    "m6g": 7, "m6i": 7, "m7g": 7,
    # compute optimised
    "c4": 8, "c5": 9, "c5n": 9, "c6g": 10, "c6i": 10, "c7g": 10,
    # memory optimised
    "r4": 11, "r5": 12, "r5a": 12, "r5n": 12,
    "r6g": 13, "r6i": 13, "r7g": 13,
    # high memory
    "x1": 15, "x2": 16,
    # GPU
    "p2": 20, "p3": 21, "p4": 22, "g4dn": 23, "g5": 24,
}

_GCP_FAMILY_TIER = {
    "e2": 1, "n1": 4, "n2": 5, "n2d": 5, "t2d": 3,
    "c2": 7, "c2d": 7, "m1": 9, "m2": 10, "m3": 11, "a2": 14,
}


def _score_ec2(it: str) -> int:
    """Score an EC2 or DB instance type string as an integer (higher = larger/more costly)."""
    # Handle "cache.t3.micro" (ElastiCache)
    if it.startswith("cache."):
        it = it[6:]
    # Handle "db.r5.4xlarge" (RDS)
    parts = it.split(".")
    if len(parts) == 3 and parts[0] == "db":
        family, size = parts[1], parts[2]
    elif len(parts) == 2:
        family, size = parts[0], parts[1]
    else:
        return -1
    tier = _EC2_FAMILY_TIER.get(family, 0)
    sz = _EC2_SIZE_ORDER.get(size, -1)
    if sz < 0:
        return -1
    return tier * 100 + sz


def _score_gcp(mt: str) -> int:
    """Score a GCP machine type like 'n2-standard-8' (higher = larger)."""
    parts = mt.split("-")
    if len(parts) < 2:
        return -1
    family = parts[0]
    vcpus = 0
    for p in reversed(parts):
        if p.isdigit():
            vcpus = int(p)
            break
    tier = _GCP_FAMILY_TIER.get(family, 0)
    return tier * 1000 + vcpus


def _cmp_direction(s_before: int, s_after: int) -> str:
    if s_before < 0 or s_after < 0:
        return "uncertain"
    if s_after > s_before:
        return "increase"
    if s_after < s_before:
        return "decrease"
    return "uncertain"


# ---------------------------------------------------------------------------
# Resource type sets
# ---------------------------------------------------------------------------

_MANAGED_DB = {
    "aws_db_instance", "aws_rds_cluster", "aws_rds_cluster_instance",
    "google_sql_database_instance",
}
_MANAGED_CACHE = {
    "aws_elasticache_cluster", "aws_elasticache_replication_group",
    "google_redis_instance",
}
_MANAGED_QUEUE = {
    "aws_sqs_queue", "google_pubsub_topic",
}
_LOAD_BALANCER = {
    "aws_lb", "aws_alb", "aws_elb",
    "google_compute_forwarding_rule", "google_compute_backend_service",
}
_NAT_GATEWAY = {
    "aws_nat_gateway", "google_compute_router_nat",
}
_UNCERTAIN_TRAFFIC = {
    "aws_cloudfront_distribution", "aws_api_gateway_rest_api",
    "aws_api_gateway_v2_api", "google_cloud_cdn",
}

_STORAGE_TIER_RANK = {
    "sc1": 0, "st1": 1, "standard": 1,
    "gp2": 2, "gp3": 3,
    "io1": 4, "io2": 5,
    "premium": 4, "ultra": 5,
    "pd-standard": 1, "pd-balanced": 2, "pd-ssd": 3, "pd-extreme": 5,
}


# ---------------------------------------------------------------------------
# Main rule evaluator
# ---------------------------------------------------------------------------

def evaluate_rules(rc: dict) -> list:
    """
    Apply all CICS rules to one resource_change dict (from Terraform plan JSON).
    Returns a list of Finding objects.
    """
    findings = []
    addr = rc.get("address", "")
    rtype = rc.get("type", "")
    change = rc.get("change", {}) or {}
    actions = change.get("actions", []) or []
    before = change.get("before") or {}
    after = change.get("after") or {}

    is_update = "update" in actions
    is_create = actions == ["create"]
    is_replace = "replace" in actions or actions == ["delete", "create"]
    is_gcp = rtype.startswith("google_")

    def _emit(emit_rule_id, category, emit_direction, severity, evidence):
        findings.append(Finding(
            rule_id=emit_rule_id, category=category, direction=emit_direction,
            severity=severity, resource_address=addr, resource_type=rtype,
            actions=list(actions), evidence=evidence,
        ))

    # -- C1 / C2 : Compute sizing -----------------------------------------
    for fld in ("instance_type", "instance_class", "machine_type",
                "node_type", "cache_node_type"):
        b, a = before.get(fld), after.get(fld)
        if b and a and b != a and (is_update or is_replace):
            if is_gcp:
                direction = _cmp_direction(_score_gcp(b), _score_gcp(a))
            else:
                direction = _cmp_direction(_score_ec2(b), _score_ec2(a))
            rule_id = "C1" if direction == "increase" else (
                "C2" if direction == "decrease" else "C1/C2")
            _emit(rule_id, "Compute sizing", direction, "high",
                  {"field": fld, "before": b, "after": a})

    # -- S1 / S3 : min scaling bounds -------------------------------------
    for fld in ("min_size", "min_count", "min_node_count", "min_replicas",
                "min_capacity"):
        b, a = before.get(fld), after.get(fld)
        if isinstance(b, (int, float)) and isinstance(a, (int, float)) \
                and b != a and is_update:
            direction = "increase" if a > b else "decrease"
            rule_id = "S1" if direction == "increase" else "S3"
            _emit(rule_id, "Scaling bounds", direction, "high",
                  {"field": fld, "before": b, "after": a})

    # -- S2 / S3 : max scaling bounds -------------------------------------
    for fld in ("max_size", "max_count", "max_node_count", "max_replicas",
                "max_capacity", "desired_capacity", "desired_count"):
        b, a = before.get(fld), after.get(fld)
        if isinstance(b, (int, float)) and isinstance(a, (int, float)) \
                and b != a and is_update:
            direction = "increase" if a > b else "decrease"
            rule_id = "S2" if direction == "increase" else "S3"
            _emit(rule_id, "Scaling bounds", direction, "medium",
                  {"field": fld, "before": b, "after": a})

    # -- ST1 : Storage capacity -------------------------------------------
    for fld in ("allocated_storage", "volume_size", "disk_size",
                "size_gb", "disk_size_gb"):
        b, a = before.get(fld), after.get(fld)
        if isinstance(b, (int, float)) and isinstance(a, (int, float)) \
                and b != a and is_update:
            direction = "increase" if a > b else "decrease"
            sev = "high" if abs(a - b) >= 50 else "medium"
            _emit("ST1", "Storage capacity", direction, sev,
                  {"field": fld, "before": b, "after": a})

    # -- ST2 : Storage tier -----------------------------------------------
    for fld in ("volume_type", "storage_type", "disk_type"):
        b, a = before.get(fld), after.get(fld)
        if b and a and b != a and is_update:
            rb = _STORAGE_TIER_RANK.get(b, -1)
            ra = _STORAGE_TIER_RANK.get(a, -1)
            if rb >= 0 and ra >= 0:
                direction = ("increase" if ra > rb else
                             "decrease" if ra < rb else "uncertain")
            else:
                direction = "uncertain"
            _emit("ST2", "Storage tier", direction, "medium",
                  {"field": fld, "before": b, "after": a})

    # -- A1 / A2 : Availability / replication -----------------------------
    b_maz, a_maz = before.get("multi_az"), after.get("multi_az")
    if b_maz is not None and a_maz is not None \
            and b_maz != a_maz and is_update:
        direction = "increase" if a_maz else "decrease"
        _emit("A1" if direction == "increase" else "A2",
              "Availability/replication", direction, "high",
              {"field": "multi_az", "before": b_maz, "after": a_maz})

    b_avt, a_avt = before.get("availability_type"), after.get("availability_type")
    if b_avt and a_avt and b_avt != a_avt and is_update:
        _order = {"ZONAL": 0, "REGIONAL": 1}
        bv, av = _order.get(b_avt, -1), _order.get(a_avt, -1)
        direction = "increase" if av > bv else "decrease" if av < bv else "uncertain"
        _emit("A1" if direction == "increase" else "A2",
              "Availability/replication", direction, "high",
              {"field": "availability_type", "before": b_avt, "after": a_avt})

    for fld in ("replica_count", "num_replicas", "replicas",
                "read_replicas_per_cluster"):
        b, a = before.get(fld), after.get(fld)
        if isinstance(b, (int, float)) and isinstance(a, (int, float)) \
                and b != a and is_update:
            direction = "increase" if a > b else "decrease"
            _emit("A1" if direction == "increase" else "A2",
                  "Availability/replication", direction, "high",
                  {"field": fld, "before": b, "after": a})

    # -- N1 : NAT / egress gateway ----------------------------------------
    if is_create and rtype in _NAT_GATEWAY:
        _emit("N1", "Networking gateway", "increase", "high",
              {"reason": "NAT/egress gateway resource created", "type": rtype})

    # -- N2 : Load balancer -----------------------------------------------
    if is_create and rtype in _LOAD_BALANCER:
        _emit("N2", "Load balancing", "increase", "high",
              {"reason": "load balancer resource created", "type": rtype})

    # -- N3 : Uncertain traffic / CDN -------------------------------------
    if is_create and rtype in _UNCERTAIN_TRAFFIC:
        _emit("N3", "Data transfer driver", "uncertain", "medium",
              {"reason": "traffic-metered resource; cost depends on usage volume",
               "type": rtype})

    # -- M1 : Managed service introduction --------------------------------
    if is_create and rtype in (_MANAGED_DB | _MANAGED_CACHE | _MANAGED_QUEUE):
        _emit("M1", "Managed service intro", "increase", "high",
              {"reason": "managed service (DB/cache/queue) created", "type": rtype})

    # -- M2 : Replacement spike -------------------------------------------
    if is_replace and rtype in (_MANAGED_DB | _LOAD_BALANCER):
        _emit("M2", "Replacement spike", "increase", "high",
              {"reason": "resource replacement implies brief double-billing and "
                         "potential disruption", "type": rtype})

    return findings
