"""Semantic retrieval with the eligibility rule kept in front of it.

Plain RAG returns whatever is nearest and lets the model decide what to do
with it. That is the half everyone has.

Here, nearness selects *candidates* and governance decides what each candidate
is permitted to do. A chunk may be the closest match in the corpus and still
be barred from supporting a cause, because it is about a different component,
because its safety review did not pass, or because it was published after the
moment being assessed. Those are three different reasons and the ledger
records which applied.

The ordering matters and is deliberate: eligibility is applied *after*
similarity, not as a pre-filter. Filtering first would hide what the model
would have chosen, and the demonstration wants to show material that was
retrieved, considered, and then not permitted to count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence
import json

from .embeddings import Embedder, cosine


# Admission bases, in descending order of what they permit.
SUPPORTS_A_CAUSE = "ENTITY_AND_SYMPTOM_MATCHED"
ENTITY_ONLY = "ENTITY_MATCHED_SYMPTOM_DIVERGES"
SEMANTIC_ONLY = "SEMANTIC_RELEVANCE_ONLY"
NOT_YET_PUBLISHED = "PUBLISHED_AFTER_ASSESSMENT"
UNSAFE = "CONTENT_SAFETY_NOT_CLEARED"


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source_id: str
    title: str
    text: str
    similarity: float
    basis: str
    may_support_cause: bool
    reliability: float
    trust_level: str
    entity_ids: tuple[str, ...]
    symptom_categories: tuple[str, ...]
    published_at: str
    rationale: str


@dataclass
class RetrievalResult:
    query: str
    provider: str
    chunks: list[RetrievedChunk] = field(default_factory=list)

    @property
    def supporting(self) -> list[RetrievedChunk]:
        return [c for c in self.chunks if c.may_support_cause]

    @property
    def context_only(self) -> list[RetrievedChunk]:
        return [c for c in self.chunks if not c.may_support_cause]


def _as_tuple(value) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return tuple(p.strip() for p in str(value or "").split(",") if p.strip())


def _date(value) -> datetime | None:
    text = str(value or "").strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None


class GovernedRetriever:
    """Semantic search over chunks, with admission decided afterwards."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or Embedder()
        self.chunks: list[dict] = []
        self.vectors: list[list[float]] = []
        self.provider = "unset"

    def index(self, chunks: Sequence[dict]) -> str:
        """Embed the corpus. Returns the provider actually used."""
        self.chunks = list(chunks)
        texts = [
            f"{c.get('title', '')}\n{c.get('text', '')}".strip()
            for c in self.chunks
        ]
        batch = self.embedder.embed(texts, task="RETRIEVAL_DOCUMENT")
        self.vectors = batch.vectors
        self.provider = batch.provider
        return self.provider

    @classmethod
    def from_jsonl(cls, path, embedder: Embedder | None = None):
        rows = [
            json.loads(line)
            for line in open(path, encoding="utf-8")
            if line.strip()
        ]
        retriever = cls(embedder)
        retriever.index(rows)
        return retriever

    def retrieve(
        self,
        query: str,
        *,
        entity_id: str | None = None,
        symptom_categories: Sequence[str] = (),
        assessed_at: datetime | None = None,
        top_k: int = 8,
    ) -> RetrievalResult:
        batch = self.embedder.embed([query], task="RETRIEVAL_QUERY")
        query_vector = batch.vectors[0]

        scored = sorted(
            (
                (cosine(query_vector, vector), chunk)
                for vector, chunk in zip(self.vectors, self.chunks)
            ),
            key=lambda pair: -pair[0],
        )[:top_k]

        presenting = {s.upper() for s in symptom_categories}
        result = RetrievalResult(query=query, provider=self.provider)

        for similarity, chunk in scored:
            entities = _as_tuple(chunk.get("entity_ids"))
            symptoms = _as_tuple(chunk.get("symptom_categories"))
            published = _date(chunk.get("published_at"))

            entity_match = bool(entity_id) and entity_id in entities
            symptom_match = bool(presenting & {s.upper() for s in symptoms})
            safe = str(chunk.get("content_safety_status", "")).upper() == "SAFE"
            in_time = not (assessed_at and published and published > assessed_at)

            # Order matters: safety and time are absolute, relevance is graded.
            if not safe:
                basis, supports = UNSAFE, False
                why = (
                    "Content safety review not cleared. Excluded from "
                    "reasoning regardless of relevance."
                )
            elif not in_time:
                basis, supports = NOT_YET_PUBLISHED, False
                why = (
                    f"Published {chunk.get('published_at')}, after the moment "
                    f"assessed. It cannot have informed a decision taken "
                    f"before it existed."
                )
            elif entity_match and symptom_match:
                basis, supports = SUPPORTS_A_CAUSE, True
                why = (
                    "About this component and this symptom. Permitted to "
                    "support a proposed cause."
                )
            elif entity_match:
                basis, supports = ENTITY_ONLY, False
                why = (
                    "About this component but a different symptom. Carried as "
                    "context; contributes nothing to the hypothesis."
                )
            else:
                basis, supports = SEMANTIC_ONLY, False
                why = (
                    "Semantically near the presentation but about another "
                    "component. Surfaced for a human to read; contributes "
                    "nothing to the hypothesis."
                )

            result.chunks.append(
                RetrievedChunk(
                    chunk_id=str(chunk.get("chunk_id", "")),
                    source_id=str(chunk.get("source_id", "")),
                    title=str(chunk.get("title", "")),
                    text=str(chunk.get("text", "")),
                    similarity=round(similarity, 4),
                    basis=basis,
                    may_support_cause=supports,
                    # Mirrors the evidence ledger: material that cannot
                    # support a cause is admitted at reduced reliability
                    # rather than discarded.
                    reliability=1.0 if supports else 0.4,
                    trust_level=str(chunk.get("trust_level", "")),
                    entity_ids=entities,
                    symptom_categories=symptoms,
                    published_at=str(chunk.get("published_at", "")),
                    rationale=why,
                )
            )
        return result
