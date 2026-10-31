"""REAL Ollama embedding-model adapter (``/api/embed``).

Status (M1): implemented against the documented Ollama HTTP API but NEVER
called during M1 (no Ollama installation per the development constraint).
"""

from __future__ import annotations

import time

import httpx

from app.adapters.base import EmbeddingResult, ProbeResult
from app.core.config import Settings
from app.core.errors import AdapterUnavailableError, UpstreamTimeoutError


class OllamaEmbeddingsAdapter:
    """Embeddings from nomic-embed-text (or configured model) via Ollama."""

    probe_name = "embeddings"
    provider_id = "ollama"
    mode = "real"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._closed = False

    @property
    def base_url(self) -> str:
        return self._settings.ollama_base_url.rstrip("/")

    @property
    def model_name(self) -> str:
        return self._settings.ollama_embed_model

    @property
    def dimensions(self) -> int:
        return self._settings.embedding_dimensions

    # -- probes -----------------------------------------------------------
    def ping(self) -> ProbeResult:
        start = time.perf_counter()
        if self._closed:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=0.0,
                detail="Ollama adapter closed",
            )
        elapsed = lambda: (time.perf_counter() - start) * 1000  # noqa: E731
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=2.0)
            response.raise_for_status()
            names = {
                m.get("name", "")
                for m in response.json().get("models", [])
                if isinstance(m, dict)
            }
        except (httpx.HTTPError, ValueError) as exc:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=elapsed(),
                detail=(
                    f"Ollama not reachable at {self.base_url} "
                    f"({type(exc).__name__}). Install/start Ollama — DEPLOYMENT.md."
                ),
            )
        wanted = self.model_name
        if wanted not in names and not any(
            n.split(":")[0] == wanted.split(":")[0] for n in names
        ):
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=elapsed(),
                detail=(
                    f"Ollama is running but embedding model '{wanted}' is not "
                    "pulled (run: ollama pull nomic-embed-text:v1.5)."
                ),
            )
        return ProbeResult(
            name=self.probe_name,
            status="ok",
            mode=self.mode,
            latency_ms=elapsed(),
            detail=f"Ollama embeddings ready (model: {wanted}, {self.dimensions}-dim)",
        )

    # -- embedding ---------------------------------------------------------
    def embed(self, texts: list[str]) -> EmbeddingResult:
        if self._closed:
            raise AdapterUnavailableError("Ollama adapter is closed.")
        if not texts:
            return EmbeddingResult(
                vectors=[], model=self.model_name, dimensions=self.dimensions, latency_ms=0.0
            )
        start = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model_name, "input": texts},
                timeout=self._settings.ollama_timeout_ms / 1000,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError(
                f"Ollama embedding request timed out after "
                f"{self._settings.ollama_timeout_ms} ms."
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterUnavailableError(
                f"Ollama embedding request to {self.base_url} failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        except ValueError as exc:
            raise AdapterUnavailableError(
                f"Ollama returned a non-JSON response: {exc}"
            ) from exc

        vectors = body.get("embeddings")
        if not isinstance(vectors, list):
            raise AdapterUnavailableError(
                "Ollama embedding response did not contain an 'embeddings' list."
            )
        dimensions = len(vectors[0]) if vectors and vectors[0] else self.dimensions
        return EmbeddingResult(
            vectors=vectors,
            model=self.model_name,
            dimensions=dimensions,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    def close(self) -> None:
        self._closed = True
