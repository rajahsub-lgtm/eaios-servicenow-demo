from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


@dataclass(frozen=True)
class ScaleSpec:
    entities: int
    relationships: int
    patterns: int
    incidents: int
    outcomes: int
    source_documents: int
    document_chunks: int
    detailed_episodes: int
    ambiguity_pairs: int
    counterfactual_pairs: int


@dataclass(frozen=True)
class GeneratorSpec:
    name: str
    seed: int
    schema_version: str
    data_classification: str
    scale: ScaleSpec
    minimum_outcome_sample: int
    transfer_ceiling: float
    prior_confidence_strategy: str
    trivial_classifier_max_accuracy: float


def load_spec(config_path: Path, profile: str) -> GeneratorSpec:
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    enterprise = raw["enterprise"]
    scale = dict(raw["scale"])
    if profile == "golden":
        scale.update(
            entities=120,
            relationships=720,
            patterns=20,
            incidents=800,
            outcomes=800,
            source_documents=80,
            document_chunks=480,
            detailed_episodes=80,
            ambiguity_pairs=6,
            counterfactual_pairs=4,
        )
    elif profile != "enterprise":
        raise ValueError(f"Unknown profile: {profile}")
    policy = raw["policy"]
    return GeneratorSpec(
        name=enterprise["name"],
        seed=int(enterprise["seed"]),
        schema_version=str(enterprise["schema_version"]),
        data_classification=enterprise["data_classification"],
        scale=ScaleSpec(**{k: int(v) for k, v in scale.items()}),
        minimum_outcome_sample=int(policy["minimum_outcome_sample"]),
        transfer_ceiling=float(policy["transfer_ceiling"]),
        prior_confidence_strategy=str(policy["prior_confidence_strategy"]),
        trivial_classifier_max_accuracy=float(policy["trivial_classifier_max_accuracy"]),
    )
