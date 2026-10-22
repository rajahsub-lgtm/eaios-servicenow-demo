import re

CITATION_PATTERN = re.compile(
    r"\b(?:TEL|LAB)-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\b"
)

LABELED_SAMPLE_PATTERN = re.compile(
    r"\bsample[_ ]id\b[\"'`*\s]*:[\"'`*\s]*"
    r"([A-Za-z0-9][A-Za-z0-9_-]*)",
    re.IGNORECASE,
)


def citation_validity(inputs, outputs):
    allowed = {
        reading["sample_id"]
        for component in inputs["evidence"]
        for reading in component.get("latest_readings", [])
    }

    brief = outputs.get("brief", "")
    cited = (
        set(CITATION_PATTERN.findall(brief))
        | set(LABELED_SAMPLE_PATTERN.findall(brief))
    )
    invalid = cited - allowed

    if not cited:
        return {
            "key": "citation_validity",
            "score": False,
            "comment": "No recognizable telemetry citations; citations required for this lab.",
        }

    return {
        "key": "citation_validity",
        "score": not invalid,
        "comment": (
            "Unknown sample citations: " + ", ".join(sorted(invalid))
            if invalid
            else f"All {len(cited)} cited telemetry IDs exist in the input."
        ),
    }
