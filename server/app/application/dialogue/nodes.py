"""
ANCHOR: app.application.dialogue.nodes
PURPOSE: LangGraph node callables placeholders (assess, clarify, retrieve, ground, answer, escalate).
Dependencies: retrieval, grounding, quality_escalation, llm port via DI
CRITICAL: Nodes must call ports — never hard-code Stub* or Http* (CS-LG-02).
DO:
- Same node functions for stub and live adapters
DONT:
- Return ungrounded final answers
"""

from __future__ import annotations

from app.application.dialogue.state import DialogueState


async def assess_specificity(state: DialogueState) -> DialogueState:
    raise NotImplementedError("assess_specificity node not implemented")


async def clarify(state: DialogueState) -> DialogueState:
    raise NotImplementedError("clarify node not implemented")


async def retrieve(state: DialogueState) -> DialogueState:
    raise NotImplementedError("retrieve node not implemented")


async def ground(state: DialogueState) -> DialogueState:
    raise NotImplementedError("ground node not implemented")


async def answer(state: DialogueState) -> DialogueState:
    raise NotImplementedError("answer node not implemented")


async def escalate(state: DialogueState) -> DialogueState:
    raise NotImplementedError("escalate node not implemented")
