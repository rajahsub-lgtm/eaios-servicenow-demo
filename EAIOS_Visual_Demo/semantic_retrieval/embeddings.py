"""Turn text into vectors, with a local fallback.

Vertex AI produces the embeddings. A deterministic local encoder stands in
when credentials or network are unavailable, so the retrieval pipeline can be
built and tested without cloud access and without spend.

The fallback is explicitly *not* a semantic model — it is a hashed bag of
character n-grams. It gives the same interface and enough signal to exercise
the plumbing, and it will not silently masquerade as real semantics: the
`provider` on every batch says which produced it, and the evaluation refuses
to report retrieval quality from fallback vectors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import hashlib
import math
import os


# text-embedding-005 at 768 dimensions. Larger models exist; at twenty
# thousand chunks the retrieval difference is small and the cost difference
# is not.
VERTEX_MODEL = "text-embedding-005"
DIMENSIONS = 768


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    provider: str
    model: str
    dimensions: int

    @property
    def is_semantic(self) -> bool:
        """False for the fallback. Guards anything that reports quality."""
        return self.provider == "vertex"


class Embedder:
    def __init__(
        self,
        project: str | None = None,
        location: str = "us-central1",
        model: str = VERTEX_MODEL,
        allow_fallback: bool = True,
    ) -> None:
        self.project = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = location
        self.model_name = model
        self.allow_fallback = allow_fallback
        self._model = None
        self._provider = "unset"

    def _load(self) -> str:
        if self._provider != "unset":
            return self._provider
        try:
            import vertexai
            from vertexai.language_models import TextEmbeddingModel

            vertexai.init(project=self.project, location=self.location)
            self._model = TextEmbeddingModel.from_pretrained(self.model_name)
            self._provider = "vertex"
        except Exception as exc:  # noqa: BLE001 — any failure means fallback
            if not self.allow_fallback:
                raise
            self._reason = str(exc)
            self._provider = "local"
        return self._provider

    def embed(
        self, texts: Sequence[str], *, task: str = "RETRIEVAL_DOCUMENT"
    ) -> EmbeddingBatch:
        """Embed a batch.

        `task` matters and is easy to get wrong. Vertex embeds a document and
        a query differently — asymmetric retrieval — and using
        RETRIEVAL_DOCUMENT for both is a common cause of retrieval that is
        mysteriously mediocre rather than obviously broken.
        """
        provider = self._load()
        if provider == "vertex":
            from vertexai.language_models import TextEmbeddingInput

            vectors: list[list[float]] = []
            # The API caps batch size; 250 is comfortably under it.
            for start in range(0, len(texts), 250):
                window = texts[start : start + 250]
                inputs = [TextEmbeddingInput(t, task) for t in window]
                vectors.extend(
                    e.values
                    for e in self._model.get_embeddings(
                        inputs, output_dimensionality=DIMENSIONS
                    )
                )
            return EmbeddingBatch(vectors, "vertex", self.model_name, DIMENSIONS)

        return EmbeddingBatch(
            [_local_vector(t) for t in texts],
            "local",
            "hashed-trigram-fallback",
            DIMENSIONS,
        )


def _local_vector(text: str, dimensions: int = DIMENSIONS) -> list[float]:
    """Deterministic hashed character trigrams, L2-normalised.

    Enough shared signal between texts that share substrings to exercise
    ranking. Not semantics — "connection pool exhaustion" and "thread
    starvation" are near-orthogonal here and close under a real model, which
    is exactly the difference the evaluation is meant to measure.
    """
    vector = [0.0] * dimensions
    cleaned = " ".join(text.lower().split())
    for i in range(max(1, len(cleaned) - 2)):
        gram = cleaned[i : i + 3]
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity.

    Direction, not magnitude — magnitude carries length rather than meaning,
    which is why this and not Euclidean distance.
    """
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
