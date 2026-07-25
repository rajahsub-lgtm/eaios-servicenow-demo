from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import json


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class VendorHealthFinding:
    """One vendor's account of one of its own services.

    Deliberately says nothing about enterprise infrastructure. A vendor can
    report that its service is healthy; it cannot report why an enterprise is
    failing to reach it.
    """

    advisory_id: str
    vendor: str
    service: str
    applies_to_entity_ids: list[str]
    status: str
    incident_confirmed: bool
    affected_scope: str
    observed_at: str
    published_at: str
    freshness_minutes: int
    is_fresh: bool
    source_authority: str
    source_reference: str
    confidence: float
    is_trusted: bool
    eliminates_external_hypothesis: bool
    disqualification_reasons: list[str]
    summary: str
    synthetic: bool


@dataclass(frozen=True)
class VendorHealthAssessment:
    scenario_id: str
    assessed_at: str
    findings: list[VendorHealthFinding]
    vendors_reporting_healthy: list[str]
    vendors_reporting_incident: list[str]
    vendors_without_usable_evidence: list[str]
    eliminated_external_hypotheses: list[str]
    explanation: str


class VendorHealthAgent:
    """Retrieve and normalise external service-health evidence.

    The agent reports vendor truth and stops there. It does not rank internal
    hypotheses, does not attribute cause, and does not touch confidence. Those
    remain the responsibility of evidence fusion and the confidence engine,
    which is the point of keeping this capability separate: vendor silence and
    internal fault are different claims and must not be merged by the
    component that gathers one of them.
    """

    def __init__(
        self,
        json_dir: str | Path,
        policy_file: str | Path | None = None,
    ) -> None:
        self.json_dir = Path(json_dir)
        self.path = self.json_dir / "vendor_advisories.json"
        policy_path = (
            Path(policy_file)
            if policy_file
            else self.json_dir.parent / "config" / "vendor_health_policy.json"
        )
        with open(policy_path, encoding="utf-8") as f:
            self.policy = json.load(f)

    def _advisories(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _dt(value: str) -> datetime:
        return datetime.strptime(value, DATETIME_FORMAT)

    def _evaluate(self, row: dict, assessed_at: datetime) -> VendorHealthFinding:
        published = self._dt(row["published_at"])
        freshness_minutes = int((assessed_at - published).total_seconds() // 60)

        maximum_age = int(self.policy["maximum_freshness_minutes"])
        trusted = set(self.policy["trusted_source_authorities"])
        minimum_confidence = float(self.policy["minimum_source_confidence"])
        healthy = set(self.policy["healthy_statuses"])

        is_fresh = 0 <= freshness_minutes <= maximum_age
        authority_ok = row["source_authority"] in trusted
        confidence_ok = float(row["confidence"]) >= minimum_confidence
        is_trusted = authority_ok and confidence_ok
        reports_healthy = row["status"] in healthy and not row["incident_confirmed"]

        reasons: list[str] = []
        if not is_fresh:
            reasons.append(
                "STALE_BEYOND_FRESHNESS_WINDOW"
                if freshness_minutes > maximum_age
                else "PUBLISHED_AFTER_ASSESSMENT"
            )
        if not authority_ok:
            reasons.append("SOURCE_AUTHORITY_NOT_TRUSTED")
        if not confidence_ok:
            reasons.append("SOURCE_CONFIDENCE_BELOW_THRESHOLD")
        if not reports_healthy:
            reasons.append("SERVICE_NOT_REPORTED_HEALTHY")

        return VendorHealthFinding(
            advisory_id=row["advisory_id"],
            vendor=row["vendor"],
            service=row["service"],
            applies_to_entity_ids=list(row.get("applies_to_entity_ids", [])),
            status=row["status"],
            incident_confirmed=bool(row["incident_confirmed"]),
            affected_scope=row.get("affected_scope", "UNKNOWN"),
            observed_at=row["observed_at"],
            published_at=row["published_at"],
            freshness_minutes=freshness_minutes,
            is_fresh=is_fresh,
            source_authority=row["source_authority"],
            source_reference=row.get("source_reference", ""),
            confidence=float(row["confidence"]),
            is_trusted=is_trusted,
            eliminates_external_hypothesis=not reasons,
            disqualification_reasons=reasons,
            summary=row.get("summary", ""),
            synthetic=row.get("data_classification") == "SYNTHETIC",
        )

    def assess(
        self,
        *,
        scenario_id: str,
        entity_ids: set[str],
        as_of: str,
    ) -> VendorHealthAssessment:
        assessed_at = self._dt(as_of)
        findings = [
            self._evaluate(row, assessed_at)
            for row in self._advisories()
            if set(row.get("applies_to_entity_ids", [])) & entity_ids
        ]
        findings.sort(key=lambda item: (item.vendor, item.advisory_id))

        healthy_vendors: list[str] = []
        incident_vendors: list[str] = []
        eliminated: list[str] = []
        for finding in findings:
            if finding.incident_confirmed and finding.is_trusted and finding.is_fresh:
                if finding.vendor not in incident_vendors:
                    incident_vendors.append(finding.vendor)
            if finding.eliminates_external_hypothesis:
                if finding.vendor not in healthy_vendors:
                    healthy_vendors.append(finding.vendor)
                # Scoped to the service the source has standing over. A record
                # covering one service never speaks for another.
                hypothesis = f"EXTERNAL_{finding.vendor.upper()}_OUTAGE"
                if hypothesis not in eliminated:
                    eliminated.append(hypothesis)

        covered = {finding.vendor for finding in findings}
        unusable = sorted(
            covered - set(healthy_vendors) - set(incident_vendors)
        )

        return VendorHealthAssessment(
            scenario_id=scenario_id,
            assessed_at=as_of,
            findings=findings,
            vendors_reporting_healthy=healthy_vendors,
            vendors_reporting_incident=incident_vendors,
            vendors_without_usable_evidence=unusable,
            eliminated_external_hypotheses=eliminated,
            explanation=(
                f"Reviewed {len(findings)} external service-health record(s). "
                f"Usable healthy evidence for {healthy_vendors or 'none'}; "
                f"confirmed vendor incidents for {incident_vendors or 'none'}. "
                "Vendor evidence describes vendor services only and does not "
                "identify an internal cause."
            ),
        )

    @staticmethod
    def to_dict(assessment: VendorHealthAssessment) -> dict:
        return asdict(assessment)
