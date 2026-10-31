"""REAL Ollama chat-model adapter (Ollama REST API, ``/api/chat``).

Status (M1): implemented against the documented Ollama HTTP API but NEVER
called during M1 (no Ollama installation per the development constraint).
``ping()`` and ``generate()`` degrade cleanly with actionable errors when the
server is absent.
"""

from __future__ import annotations

import logging
import time

import httpx

from app.adapters.base import ModelResult, ProbeResult
from app.core.config import Settings
from app.core.errors import AdapterUnavailableError, UpstreamTimeoutError

logger = logging.getLogger(__name__)


class OllamaChatAdapter:
    """Chat completions from a locally running Ollama server."""

    probe_name = "llm"
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
        return self._settings.ollama_llm_model

    # -- probes -----------------------------------------------------------
    def _list_models(self) -> tuple[set[str], str | None]:
        """Return the set of local model names, or an error string."""
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=2.0)
            response.raise_for_status()
            payload = response.json()
            names = {
                model.get("name", "")
                for model in payload.get("models", [])
                if isinstance(model, dict)
            }
            return names, None
        except httpx.HTTPError as exc:
            return set(), f"{type(exc).__name__}: {exc}"
        except ValueError as exc:
            return set(), f"invalid response: {exc}"

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

        names, error = self._list_models()
        if error is not None:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=elapsed(),
                detail=(
                    f"Ollama not reachable at {self.base_url} ({error}). "
                    "Install Ollama and start the service — see DEPLOYMENT.md."
                ),
            )
        wanted = self.model_name
        if wanted not in names and not any(
            n == wanted or n.split(":")[0] == wanted.split(":")[0] for n in names
        ):
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=elapsed(),
                detail=(
                    f"Ollama is running but model '{wanted}' is not pulled "
                    "(run: ollama pull granite4.2:3b)."
                ),
            )
        return ProbeResult(
            name=self.probe_name,
            status="ok",
            mode=self.mode,
            latency_ms=elapsed(),
            detail=f"Ollama ready at {self.base_url} (model: {wanted})",
        )

    # -- generation --------------------------------------------------------
    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> ModelResult:
        if self._closed:
            raise AdapterUnavailableError("Ollama adapter is closed.")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        start = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self._settings.ollama_timeout_ms / 1000,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError(
                f"Ollama generation timed out after "
                f"{self._settings.ollama_timeout_ms} ms."
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterUnavailableError(
                f"Ollama request to {self.base_url} failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        except ValueError as exc:
            raise AdapterUnavailableError(
                f"Ollama returned a non-JSON response: {exc}"
            ) from exc

        content = (body.get("message") or {}).get("content", "")
        usage = {}
        if "prompt_eval_count" in body:
            usage["prompt_tokens"] = int(body["prompt_eval_count"])
        if "eval_count" in body:
            usage["completion_tokens"] = int(body["eval_count"])
        return ModelResult(
            text=content,
            model=self.model_name,
            latency_ms=(time.perf_counter() - start) * 1000,
            usage=usage or None,
        )

    def close(self) -> None:
        self._closed = True
