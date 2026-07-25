from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any
import json
import uuid


UTC = timezone.utc


@dataclass(frozen=True)
class PolicyRequest:
    correlation_id: str
    request_type: str
    requesting_agent_id: str
    action: str
    resource_id: str
    skill_id: str
    operation_mode: str
    data_domain: str | None
    data_classification: str
    purpose: str


@dataclass(frozen=True)
class PolicyDecision:
    decision_id: str
    policy_id: str
    decision: str
    obligations: list[str]
    reason: str
    request: PolicyRequest
    decided_at: str


class PolicyDecisionPoint:
    """Minimal PDP for the demo's A2A, MCP, and data-access seams."""

    def __init__(
        self,
        policy_file: str | Path,
        agent_registry_file: str | Path,
        skill_catalog_file: str | Path,
    ) -> None:
        self.policy = self._read(Path(policy_file))
        self.registry = self._read(Path(agent_registry_file))
        self.skill_catalog = self._read(Path(skill_catalog_file))
        self.agents = {
            row["agent_id"]: row for row in self.registry["agents"]
        }
        self.skills = {
            row["skill_id"] for row in self.skill_catalog["skills"]
        }
        self.policies = sorted(
            self.policy["policies"],
            key=lambda row: int(row.get("priority", 0)),
            reverse=True,
        )

    @staticmethod
    def _read(path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="milliseconds")

    def decide(self, request: PolicyRequest) -> PolicyDecision:
        agent = self.agents.get(request.requesting_agent_id)

        for policy in self.policies:
            if not self._matches(policy, request, agent):
                continue
            return PolicyDecision(
                decision_id=f"PDP-{uuid.uuid4().hex[:12].upper()}",
                policy_id=policy["policy_id"],
                decision=policy["decision"],
                obligations=list(policy.get("obligations", [])),
                reason=(
                    f"Matched {policy['policy_id']} for "
                    f"{request.request_type}:{request.action} on "
                    f"{request.resource_id}."
                ),
                request=request,
                decided_at=self._now(),
            )

        return PolicyDecision(
            decision_id=f"PDP-{uuid.uuid4().hex[:12].upper()}",
            policy_id="DEFAULT",
            decision=self.policy.get("default_decision", "DENY"),
            obligations=["LOG_ACCESS"],
            reason="No explicit allow or escalation policy matched.",
            request=request,
            decided_at=self._now(),
        )

    def _matches(
        self,
        policy: dict,
        request: PolicyRequest,
        agent: dict | None,
    ) -> bool:
        if policy.get("request_type") != request.request_type:
            return False
        if request.action not in policy.get("actions", []):
            return False

        required_status = policy.get("agent_status")
        if required_status and (
            agent is None or agent.get("status") != required_status
        ):
            return False

        if policy.get("skill_must_be_registered"):
            if (
                agent is None
                or request.skill_id not in self.skills
                or request.skill_id not in set(agent.get("skills", []))
            ):
                return False

        if policy.get("tool_must_be_registered_to_agent"):
            if (
                agent is None
                or request.resource_id not in set(agent.get("mcp_tools", []))
            ):
                return False

        if policy.get("data_domain_must_be_registered_to_agent"):
            if (
                agent is None
                or request.data_domain not in set(agent.get("data_domains", []))
            ):
                return False

        modes = policy.get("operation_modes")
        if modes and request.operation_mode not in modes:
            return False

        classifications = policy.get("allowed_classifications")
        if classifications and request.data_classification not in classifications:
            return False

        patterns = policy.get("resource_patterns")
        if patterns and not any(
            fnmatch(request.resource_id, pattern) for pattern in patterns
        ):
            return False

        return True

    @staticmethod
    def to_dict(decision: PolicyDecision) -> dict:
        return asdict(decision)


class PolicyEnforcementError(PermissionError):
    pass


class BaseEnforcementPoint:
    """PEP that invokes the PDP, applies the decision, and records an audit."""

    def __init__(
        self,
        pep_name: str,
        pdp: PolicyDecisionPoint,
        audit_log: list[PolicyDecision],
    ) -> None:
        self.pep_name = pep_name
        self.pdp = pdp
        self.audit_log = audit_log

    def enforce(self, request: PolicyRequest) -> PolicyDecision:
        decision = self.pdp.decide(request)
        self.audit_log.append(decision)

        if decision.decision == "DENY":
            raise PolicyEnforcementError(
                f"{self.pep_name} denied {request.action} on "
                f"{request.resource_id}: {decision.reason}"
            )
        return decision


class A2AEnforcementPoint(BaseEnforcementPoint):
    def __init__(self, pdp, audit_log):
        super().__init__("A2A PEP", pdp, audit_log)


class MCPEnforcementPoint(BaseEnforcementPoint):
    def __init__(self, pdp, audit_log):
        super().__init__("MCP PEP", pdp, audit_log)


class DataAccessEnforcementPoint(BaseEnforcementPoint):
    def __init__(self, pdp, audit_log):
        super().__init__("Data Access PEP", pdp, audit_log)
