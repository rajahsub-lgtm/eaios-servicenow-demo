"""What a validator reports, and how severity is decided.

A finding names the rule it violates, the record that violates it, and what
that would cause. "Referential integrity failure" is not a useful report; "the
outcome OUT-0412 references pattern KE-QUEUE-999, which does not exist, so the
ledger will silently count zero cases for it" is.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import json


class Severity(str, Enum):
    """Three levels, and the distinction is about consequence.

    ERROR   the dataset is wrong and will produce visibly incoherent
            behaviour. Blocks release.
    WARN    the dataset is coherent but unrealistic, or an invariant is
            weakly held. Worth knowing; does not block.
    INFO    an observation carried for the record — distributions,
            population counts, and the shape of what was generated.
    """

    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"


@dataclass(frozen=True)
class Finding:
    validator: str
    rule: str
    severity: Severity
    summary: str
    subject: str = ""
    consequence: str = ""
    detail: dict = field(default_factory=dict)

    def line(self) -> str:
        head = f"[{self.severity.value}] {self.validator}·{self.rule}"
        subject = f" ({self.subject})" if self.subject else ""
        text = f"{head}{subject}: {self.summary}"
        if self.consequence:
            text += f"\n         → {self.consequence}"
        return text


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def extend(self, findings) -> None:
        self.findings.extend(findings)

    def of(self, severity: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity is severity]

    @property
    def errors(self) -> list[Finding]:
        return self.of(Severity.ERROR)

    @property
    def warnings(self) -> list[Finding]:
        return self.of(Severity.WARN)

    @property
    def passed(self) -> bool:
        return not self.errors

    def by_validator(self) -> dict[str, dict[str, int]]:
        summary: dict[str, dict[str, int]] = {}
        for finding in self.findings:
            bucket = summary.setdefault(
                finding.validator, {"ERROR": 0, "WARN": 0, "INFO": 0}
            )
            bucket[finding.severity.value] += 1
        return summary

    def to_json(self) -> str:
        return json.dumps(
            {
                "passed": self.passed,
                "counts": {
                    "error": len(self.errors),
                    "warn": len(self.warnings),
                    "info": len(self.of(Severity.INFO)),
                },
                "by_validator": self.by_validator(),
                "findings": [
                    {**asdict(f), "severity": f.severity.value}
                    for f in self.findings
                ],
            },
            indent=2,
        )


def error(validator: str, rule: str, summary: str, **kw) -> Finding:
    return Finding(validator, rule, Severity.ERROR, summary, **kw)


def warn(validator: str, rule: str, summary: str, **kw) -> Finding:
    return Finding(validator, rule, Severity.WARN, summary, **kw)


def info(validator: str, rule: str, summary: str, **kw) -> Finding:
    return Finding(validator, rule, Severity.INFO, summary, **kw)
