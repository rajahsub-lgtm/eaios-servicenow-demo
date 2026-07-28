from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .generate import generate_dataset
from .spec import load_spec
from .validate import validate_dataset


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate and validate EAIOS synthetic enterprise datasets")
    sub = p.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--profile", choices=["golden", "enterprise"], required=True)
    gen.add_argument("--output", type=Path, required=True)
    gen.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config" / "enterprise.yaml")
    val = sub.add_parser("validate")
    val.add_argument("--profile", choices=["golden", "enterprise"], required=True)
    val.add_argument("--dataset", type=Path, required=True)
    val.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config" / "enterprise.yaml")
    return p


def main() -> int:
    args = parser().parse_args()
    spec = load_spec(args.config, args.profile)
    if args.command == "generate":
        args.output.mkdir(parents=True, exist_ok=True)
        manifest = generate_dataset(spec, args.output)
        report = validate_dataset(spec, args.output)
        print(json.dumps({"manifest": manifest, "validation": report}, indent=2))
        return 0 if report["status"] == "PASS" else 2
    report = validate_dataset(spec, args.dataset)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
