from __future__ import annotations

from pathlib import Path
import argparse
import json
import re

from servicenow_table_client import ServiceNowCredentials, ServiceNowTableClient


ROOT = Path(__file__).resolve().parent


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def build_suggestions(mapping: dict, discovered: list[dict]) -> dict:
    label_index: dict[str, list[dict]] = {}
    for row in discovered:
        label = str(row.get("column_label", ""))
        label_index.setdefault(normalize(label), []).append(row)

    result = json.loads(json.dumps(mapping))
    matched = 0
    ambiguous = 0
    for concept, rule in result["fields"].items():
        candidates = []
        for alias in rule.get("aliases", [concept]):
            candidates.extend(label_index.get(normalize(alias), []))
        unique = {str(row.get("element")): row for row in candidates if row.get("element")}
        if len(unique) == 1:
            row = next(iter(unique.values()))
            rule["suggested_internal_name"] = row["element"]
            rule["suggested_label"] = row.get("column_label", "")
            rule["dictionary_type"] = row.get("internal_type", "")
            rule["suggestion_basis"] = "EXACT_NORMALIZED_LABEL"
            matched += 1
        elif len(unique) > 1:
            rule["ambiguous_candidates"] = sorted(unique)
            rule["suggestion_basis"] = "AMBIGUOUS_EXACT_LABEL"
            ambiguous += 1
        else:
            rule["suggestion_basis"] = "NO_EXACT_LABEL_MATCH"

    result["status"] = "REVIEW_REQUIRED"
    result["discovery_summary"] = {
        "dictionary_fields_found": len(discovered),
        "exact_suggestions": matched,
        "ambiguous_concepts": ambiguous,
        "important": "Suggestions are not confirmed mappings. Review in the PDI before live writes.",
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mapping",
        default="config/servicenow_field_mapping.json",
    )
    args = parser.parse_args()

    mapping_path = ROOT / args.mapping
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    client = ServiceNowTableClient(ServiceNowCredentials.from_env())
    discovered = client.discover_dictionary_fields(mapping["target_table"])

    outputs = ROOT / "outputs"
    outputs.mkdir(exist_ok=True)
    dictionary_path = outputs / "servicenow_dictionary_fields.json"
    suggestion_path = outputs / "servicenow_field_mapping.suggested.json"
    dictionary_path.write_text(json.dumps(discovered, indent=2), encoding="utf-8")
    suggestion_path.write_text(
        json.dumps(build_suggestions(mapping, discovered), indent=2),
        encoding="utf-8",
    )

    print(f"Dictionary fields discovered: {len(discovered)}")
    print(f"Saved: {dictionary_path}")
    print(f"Saved reviewable suggestions: {suggestion_path}")
    print("Review each suggestion, copy approved internal names into the main mapping, and set confirmed=true.")


if __name__ == "__main__":
    main()
