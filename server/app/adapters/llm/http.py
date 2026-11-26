"""
ANCHOR: app.adapters.llm.HttpLLMClient
PURPOSE: Real HttpLLMClient — OpenAI-compatible chat completions behind flags.
Dependencies: httpx; Settings
CRITICAL: Always used — real OpenAI-compatible chat client.
DO:
- Enforce *_TIMEOUT_S on clients
- Map failures to typed errors without leaking secrets
- Strip <think>…</think> before classify_specificity label matching
DONT:
- Call from application without DI factory
- Match specificity labels inside model reasoning / chain-of-thought
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.adapters.llm.port import LLMClient
from app.domain.errors import AppError, UpstreamTimeoutError

_THINK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_LABELS = ("underspecified", "ambiguous", "specific")


def strip_think_blocks(text: str) -> str:
    """Remove model chain-of-thought wrappers before downstream classification."""
    return _THINK_RE.sub("", text or "").strip()


def parse_specificity_label(raw: str) -> str:
    """
    Map classifier output to underspecified|ambiguous|specific.

    Strips <think> blocks first so reasoning that mentions 'underspecified'
    cannot override the final token (API clarifying vs direct-answer bug).
    """
    cleaned = strip_think_blocks(raw).lower()
    # Prefer an exact single-token / first-line match.
    first = cleaned.splitlines()[0].strip() if cleaned else ""
    token = first.split()[0].strip(".,;:\"'`") if first else ""
    if token in _LABELS:
        return token
    for label in _LABELS:
        if re.search(rf"\b{label}\b", cleaned):
            return label
    return "specific"


class HttpLLMClient:
    """OpenAI-compatible chat client."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_s: float = 180.0,
        temperature: float = 0.2,
        max_tokens: int = 1500,
        allow_hosts: set[str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_s
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._allow_hosts = allow_hosts or set()
        self._assert_host_allowed()

    def _assert_host_allowed(self) -> None:
        if not self._allow_hosts:
            return
        host = (urlparse(self._base_url).hostname or "").lower()
        if host and host not in self._allow_hosts:
            raise AppError(f"LLM host not allowlisted: {host}", code="EGRESS_DENIED")

    async def ping(self) -> bool:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with httpx.AsyncClient(timeout=min(self._timeout, 15.0)) as client:
                resp = await client.get(f"{self._base_url}/models", headers=headers)
                if resp.status_code < 500:
                    return True
                return False
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("LLM ping timed out") from exc
        except httpx.HTTPError as exc:
            raise AppError("LLM ping failed", code="UPSTREAM_ERROR") from exc

    async def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self._model,
            "temperature": self._temperature if temperature is None else temperature,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return str(data["choices"][0]["message"]["content"])
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("LLM request timed out") from exc
        except httpx.HTTPError as exc:
            raise AppError("LLM upstream error", code="UPSTREAM_ERROR") from exc

    async def classify_specificity(
        self, user_message: str, history: list[str] | None = None
    ) -> str:
        hist = "\n".join(history or [])
        prompt = (
            "Classify the user question as one of: underspecified, ambiguous, specific. "
            "Reply with only that single token.\n"
            f"History:\n{hist}\nQuestion:\n{user_message}"
        )
        raw = await self.complete(system="Classifier", user=prompt, temperature=0.0)
        return parse_specificity_label(raw)


_: LLMClient = HttpLLMClient(  # type: ignore[assignment]
    base_url="https://example.invalid/v1",
    api_key=None,
    model="protocol-check",
)
