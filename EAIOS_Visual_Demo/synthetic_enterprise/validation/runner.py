"""Run every validator over a dataset and report.

    python -m synthetic_enterprise.validation.runner json/
    python -m synthetic_enterprise.validation.runner generated/golden-001 --json report.json

Exit code is 1 when any ERROR is present, so this can gate a build.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import sys

from . import referential, temporal
from .dataset import Dataset
from .findings import Report, Severity, info


VALIDATORS = (
    ("referential", referential.validate),
    ("temporal", temporal.validate),
)


def run(root: str | Path) -> tuple[Dataset, Report]:
    dataset = Dataset.load(root)
    report = Report()

    counts = dataset.counts()
    report.add(
        info(
            "dataset",
            "loaded",
            ", ".join(f"{k} {v}" for k, v in counts.items()) or "nothing loaded",
            subject=str(dataset.root),
            detail={"counts": counts, "ground_truth": dataset.truth_counts()},
        )
    )

    for _, validate in VALIDATORS:
        report.extend(validate(dataset))
    return dataset, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="dataset directory")
    parser.add_argument("--json", help="write the full report here")
    parser.add_argument(
        "--quiet", action="store_true", help="suppress INFO findings"
    )
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    dataset, report = run(args.root)

    print(f"\n{'=' * 74}\nCOHERENCE VALIDATION · {dataset.root}\n{'=' * 74}")
    for finding in report.findings:
        if args.quiet and finding.severity is Severity.INFO:
            continue
        print(finding.line())

    print(f"\n{'-' * 74}")
    for name, counts in sorted(report.by_validator().items()):
        print(
            f"  {name:16} {counts['ERROR']:>3} error  "
            f"{counts['WARN']:>3} warn  {counts['INFO']:>3} info"
        )
    print(f"{'-' * 74}")
    print("PASS" if report.passed else f"FAIL — {len(report.errors)} error(s)")

    if args.json:
        Path(args.json).write_text(report.to_json(), encoding="utf-8")
        print(f"report written to {args.json}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
