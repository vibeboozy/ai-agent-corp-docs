"""
ANCHOR: app.adapters.stubs.llm
PURPOSE: StubLLMClient — deterministic classify/complete for dialogue nodes.
Dependencies: app.adapters.llm.port.LLMClient
DO:
- Keep offline and side-effect free
DONT:
- Perform real network I/O
"""

from __future__ import annotations

from app.adapters.llm.port import LLMClient

_AMBIGUOUS_MARKERS = ("кто подписывает", "кто подписывает?", "подписать договор")
_SPECIFIC_MARKERS = ("закупк", "подрядчик", "отпуск", "миллион", "смет")
_VAGUE = ("помогите", "что делать", "не знаю", "вопрос", "расскажи")


class StubLLMClient:
    """Heuristic stub LLM for specificity + grounded drafting."""

    async def ping(self) -> bool:
        return True

    async def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
    ) -> str:
        _ = (system, temperature)
        # If caller passed chunk context after "CHUNK:", echo grounded paraphrase.
        if "CHUNK:" in user:
            parts = user.split("CHUNK:", 1)[1].strip()
            return f"Согласно регламенту: {parts}"
        return "Заглушка LLM: ответ не сформирован."

    async def classify_specificity(
        self, user_message: str, history: list[str] | None = None
    ) -> str:
        text = user_message.strip().lower()
        hist = " ".join(history or []).lower()
        combined = f"{hist} {text}".strip()

        # After clarification providing domain keywords → specific
        if any(m in combined for m in _SPECIFIC_MARKERS) and any(
            m in text for m in ("закупк", "подрядчик", "отпуск", "миллион", "смет", "договор")
        ):
            # Still ambiguous if both procurement and contractor without preference
            has_proc = "закупк" in combined
            has_contr = "подрядчик" in combined
            if has_proc and has_contr and "закупк" not in text and "подрядчик" not in text:
                return "ambiguous"
            if has_proc or has_contr or "отпуск" in combined:
                return "specific"

        if any(m in text for m in _AMBIGUOUS_MARKERS):
            # Bare "кто подписывает договоры" without domain → ambiguous
            if not any(m in text for m in ("закупк", "подрядчик", "отпуск")):
                return "ambiguous"

        if len(text) < 12 or any(v in text for v in _VAGUE):
            return "underspecified"

        if any(m in text for m in _SPECIFIC_MARKERS):
            return "specific"

        # Unknown-but-specific looking questions still go to retrieve (may escalate)
        if len(text.split()) >= 4:
            return "specific"
        return "underspecified"


_: LLMClient = StubLLMClient()  # type: ignore[assignment]
