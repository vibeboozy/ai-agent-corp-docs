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

# Common CoT wrappers; also drop unclosed <think>… tails.
_THINK_RE = re.compile(
    r"<think>.*?</think>|<thinking>.*?</thinking>|"
    r"<think>.*$|<thinking>.*$",
    re.IGNORECASE | re.DOTALL,
)
_LABELS = ("underspecified", "ambiguous", "specific")
# When several labels appear in leftover prose, prefer answering over clarifying.
_LABEL_PREFERENCE = ("specific", "ambiguous", "underspecified")


def strip_think_blocks(text: str) -> str:
    """Remove model chain-of-thought wrappers before downstream classification."""
    return _THINK_RE.sub("", text or "").strip()


def parse_specificity_label(raw: str) -> str:
    """
    Map classifier output to underspecified|ambiguous|specific.

    Strips <think> blocks first so reasoning that mentions 'underspecified'
    cannot override the final token (API clarifying vs direct-answer bug).

    If multiple labels remain in cleaned text, prefer the *last* mention
    (models often reason then conclude); ties broken toward `specific`.
    """
    cleaned = strip_think_blocks(raw).lower()
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    # Bare single-line label (e.g. "specific" / "Underspecified.").
    if len(lines) == 1:
        token = lines[0].split()[0].strip(".,;:\"'`")
        if token in _LABELS and len(lines[0].split()) <= 2:
            return token
    matches: list[tuple[int, str]] = []
    for label in _LABELS:
        for m in re.finditer(rf"\b{label}\b", cleaned):
            matches.append((m.start(), label))
    if not matches:
        return "specific"
    # Last mention wins (final answer after reasoning); prefer specific on ties.
    matches.sort(key=lambda item: (item[0], -_LABEL_PREFERENCE.index(item[1])))
    return matches[-1][1]


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
        reasoning_tokens: int = 0,
        allow_hosts: set[str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_s
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._reasoning_tokens = max(0, int(reasoning_tokens))
        self._allow_hosts = allow_hosts or set()
        self._assert_host_allowed()

    @property
    def request_max_tokens(self) -> int:
        """Completion budget sent upstream: LLM_MAX_TOKENS + LLM_REASONING_TOKENS."""
        return self._max_tokens + self._reasoning_tokens

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
            "max_tokens": self.request_max_tokens,
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
            "Classify the user question as one of: underspecified, ambiguous, specific.\n"
            "Rules:\n"
            "- specific: asks who/what for a concrete role+topic "
            "(e.g. кто отвечает за организацию отчётности по проекту, "
            "кто подписывает договоры на закупку). Prefer specific when both "
            "a role-seeking cue and a concrete topic are present.\n"
            "- ambiguous: could map to two+ distinct regulation scopes "
            "(e.g. кто подписывает договоры — закупка vs подряд).\n"
            "- underspecified: missing topic or too vague to retrieve "
            "(e.g. кто отвечает за организацию?).\n"
            "Use History: a short clarification that completes a prior role+topic "
            "question is specific.\n"
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
