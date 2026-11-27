"""
ANCHOR: tests.application.test_golden_set
PURPOSE: Offline coverage of server/tests/fixtures/golden-set.md (GS-01…GS-16).
Dependencies: dialogue graph; GroundingService; Fake LLM/embeddings/vectorstore
DONT: live Qdrant / network — retrieval hits are fixtures from corpus quotes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.dialogue.graph import build_dialogue_graph
from app.application.dialogue.nodes import DialogueDeps
from app.application.dialogue.offtopic import is_off_topic
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService
from app.domain.glossary import AbbreviationGlossary

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "golden-set.md"
)

# --- Corpus-aligned hit fixtures (from docs/golden-set + corpus-samples) ---

_HIT_DBRCT_15 = {
    "document_id": "dbrct",
    "chunk_id": "c-1.5",
    "text": (
        "1.5. Заявка должна быть инициирована не менее чем за 3 рабочих дня "
        "до подачи предложения Заказчику. При невыполнении сроков Заявка отклоняется "
        "или выполняются работы со стороны SS и АМ по продлению сроков выдачи."
    ),
    "score": 0.72,
    "document_title": (
        "Проектная деятельность ДБРЦТ "
        "(Департамента бизнес-решений и цифровой трансформации)"
    ),
    "locator": "1.5.",
    "source": "ingest",
}

_HIT_PURCHASE_95 = {
    "document_id": "presale-dib",
    "chunk_id": "c-9.5",
    "text": (
        "9.5. Все субподрядные договоры по ИБ проектам, кроме перепродажи "
        "вендорских сервисов, заключаются от юридических лиц Компании."
    ),
    "score": 0.55,
    "document_title": "Пресейловая деятельность Дирекции ИБ",
    "locator": "9.5.",
    "source": "ingest",
}

_HIT_JUNK_SIGNED = {
    "document_id": "dib-project",
    "chunk_id": "junk-9.1",
    "text": "1. подписан договор на услуги с заказчиком",
    "score": 0.69,
    "document_title": "Проектная деятельность Дирекции ИБ",
    "locator": "9.1.",
    "source": "ingest",
}

_HIT_RP_27 = {
    "document_id": "dib-project",
    "chunk_id": "c-2.7",
    "text": (
        "Если предоставлена полная информация, Координатор департамента назначает РП "
        "в соответствии с итоговым Расчётом проекта в течение 1 рабочего дня."
    ),
    "score": 0.80,
    "document_title": "Проектная деятельность Дирекции ИБ",
    "locator": "2.7.",
    "source": "ingest",
}

_HIT_NEIGHBOR_FULL_INFO = {
    "document_id": "presale-dib",
    "chunk_id": "c-neighbor",
    "text": (
        "Дирекция ИБ обеспечивает предоставление полной информации по проектам "
        "в рамках пресейловой деятельности подразделения."
    ),
    "score": 0.70,
    "document_title": "Пресейловая деятельность Дирекции ИБ",
    "locator": "1.1.",
    "source": "ingest",
}

_HIT_OTCHETNOST = {
    "document_id": "tech-dir",
    "chunk_id": "c-18.1",
    "text": "18.1. За организацию отчетности по проекту отвечает Руководитель проекта.",
    "score": 0.90,
    "document_title": "Организация проектной деятельности",
    "locator": "18.1.",
    "source": "ingest",
}

_HIT_PA_51 = {
    "document_id": "presale-dib",
    "chunk_id": "c-5.1",
    "text": "5.1. ПА обязан принять заявку в работу в течение 1 рабочего дня с момента назначения.",
    "score": 0.88,
    "document_title": "Пресейловая деятельность Дирекции ИБ",
    "locator": "5.1.",
    "source": "ingest",
}

_HIT_PA_NEIGHBOR_66 = {
    "document_id": "presale-dib",
    "chunk_id": "c-6.6",
    "text": (
        "6.6. Если SS другого ЦК не отвечает в течение 1 рабочего дня, "
        "то вопрос эскалируется до его руководителя."
    ),
    "score": 0.75,
    "document_title": "Пресейловая деятельность Дирекции ИБ",
    "locator": "6.6.",
    "source": "ingest",
}

_HIT_DBRCT_101 = {
    "document_id": "dbrct",
    "chunk_id": "c-10.1",
    "text": (
        "10.1. После подписания договора (или срабатывания исключения в рамках п. 8.4 – "
        "наличия гарантийного письма и согласования Директора направления на старт работ) "
        "РП создаёт проект в системе управления проектами в течение 1 рабочего дня."
    ),
    "score": 0.70,
    "document_title": "Проектная деятельность ДБРЦТ",
    "locator": "10.1.",
    "source": "ingest",
}

_HIT_DBRCT_102_SMETA = {
    "document_id": "dbrct",
    "chunk_id": "c-10.2",
    "text": (
        "10.2. После подписания договора РП создаёт Смету в учётной системе "
        "в течение 3 рабочих дней."
    ),
    "score": 0.68,
    "document_title": "Проектная деятельность ДБРЦТ",
    "locator": "10.2.",
    "source": "ingest",
}

_HIT_BUDGET_WEAK = {
    "document_id": "presale-dib",
    "chunk_id": "c-budget",
    "text": (
        "Согласование Директора по бюджету подразделения проводится "
        "ежегодно в рамках планирования расходов и утверждения лимитов."
    ),
    "score": 0.47,
    "document_title": "Пресейловая деятельность Дирекции ИБ",
    "locator": "3.1.",
    "source": "ingest",
}

_HIT_MARGIN_NO_NUMBER = {
    "document_id": "presale-dib",
    "chunk_id": "c-14.4",
    "text": (
        "14.4. Если итоговая маржинальность услуг не достигает целевой, АМ должен "
        "согласовать Спецификацию в соответствии с внутренним регламентом "
        "контроля маржинальности сделок."
    ),
    "score": 0.82,
    "document_title": "Пресейловая деятельность Дирекции ИБ",
    "locator": "14.4.",
    "source": "ingest",
}

_HIT_DBRCT_17_SLA = {
    "document_id": "dbrct",
    "chunk_id": "c-1.7",
    "text": (
        "1.7. В случае подключения к оценке Подрядчика необходимо дополнительно "
        "учитывать SLA на поиск и согласование подрядчика."
    ),
    "score": 0.78,
    "document_title": "Проектная деятельность ДБРЦТ",
    "locator": "1.7.",
    "source": "ingest",
}


class _FakeLLM:
    def __init__(self, *, label: str, draft: str = "UNSUPPORTED") -> None:
        self._label = label
        self._draft = draft
        self.complete = AsyncMock(side_effect=self._complete)

    async def _complete(
        self, *, system: str, user: str, temperature: float | None = None
    ) -> str:
        _ = (system, temperature)
        if "Reason:" in user or "уточн" in (system or "").lower():
            return "Уточните, пожалуйста, тему или подразделение."
        return self._draft

    async def classify_specificity(
        self, user_message: str, history: list[str] | None = None
    ) -> str:
        _ = (user_message, history)
        return self._label


class _FakeEmbeddings:
    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]

    async def embed_sparse(self, texts: list[str]) -> list[dict[str, float]]:
        return [{"t": 1.0} for _ in texts]


class _FakeVectorStore:
    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self._hits = hits

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        dense_vector: list[float] | None = None,
        sparse_vector: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        _ = (query, limit, dense_vector, sparse_vector)
        return list(self._hits)


def _grounding() -> GroundingService:
    return GroundingService(
        min_citations=1,
        min_score=0.25,
        min_query_overlap=0.12,
        glossary=AbbreviationGlossary.from_defaults(),
    )


def _graph(
    *,
    label: str,
    hits: list[dict[str, Any]],
    draft: str = "UNSUPPORTED",
) -> Any:
    return build_dialogue_graph(
        DialogueDeps(
            llm=_FakeLLM(label=label, draft=draft),
            retrieval=RetrievalService(
                embeddings=_FakeEmbeddings(),
                vectorstore=_FakeVectorStore(hits),
                lexical_weight=0.35,
            ),
            grounding=_grounding(),
            quality_email="quality@example.invalid",
        )
    )


def _parse_golden_ids(text: str) -> list[str]:
    return re.findall(r"\*\*id:\*\*\s*`?(GS-\d+)`?", text)


def test_golden_set_fixture_lists_all_sixteen_cases() -> None:
    assert _FIXTURE.is_file(), f"missing fixture {_FIXTURE}"
    text = _FIXTURE.read_text(encoding="utf-8")
    ids = _parse_golden_ids(text)
    assert ids == [f"GS-{i:02d}" for i in range(1, 17)]
    for scenario in ("answer", "clarify", "escalate", "refuse"):
        assert f"· {scenario} ·" in text or f"scenario:** `{scenario}`" in text


# --- GS-01…07 answer (grounding / graph) ---


def test_gs01_dbrct_presale_three_working_days() -> None:
    q = (
        "За сколько рабочих дней нужно инициировать заявку на пресейл в ДБРЦТ?"
    )
    result = _grounding().ground(
        candidates=[_HIT_DBRCT_15], draft=None, query=q
    )
    assert result.ok, result
    assert "3" in (result.answer_text or "")
    assert "рабоч" in (result.answer_text or "").lower()
    assert "1.5" in (result.answer_text or "")


def test_gs02_purchase_signer_not_checklist_junk() -> None:
    q = "Кто подписывает договоры на закупку?"
    result = _grounding().ground(
        candidates=[_HIT_JUNK_SIGNED, _HIT_PURCHASE_95],
        draft="Ответ: Подписан договор на услуги с заказчиком.",
        query=q,
    )
    assert result.ok, result
    first = (result.answer_text or "").splitlines()[0]
    assert "Юридические лица Компании" in first
    assert "подписан договор на услуги" not in first.lower()
    assert result.citations[0]["locator"] == "9.5"


def test_gs03_when_rp_q1_coordinator_calculation() -> None:
    q = (
        "В течение какого срока Координатор департамента назначает РП "
        "при наличии полного Расчёта проекта?"
    )
    result = _grounding().ground(
        candidates=[_HIT_RP_27],
        draft="Ответ: В течение одного рабочего дня.",
        query=q,
    )
    assert result.ok, result
    assert "рабочего дня" in (result.answer_text or "").lower()
    assert "2.7" in (result.answer_text or "")


def test_gs04_when_rp_q2_near_duplicate_morphology() -> None:
    q = (
        "За сколько назначается РП в Дирекции ИБ "
        "при предоставлении полной информации?"
    )
    result = _grounding().ground(
        candidates=[_HIT_NEIGHBOR_FULL_INFO, _HIT_RP_27],
        draft="Ответ: В течение одного рабочего дня.",
        query=q,
    )
    assert result.ok, result
    assert "рабочего дня" in (result.answer_text or "").lower()
    assert result.citations[0]["chunk_id"] == "c-2.7"
    # Day count must survive strip_regulation_noise («1» not eaten as clause #).
    extracted = (result.answer_text or "").splitlines()[0]
    assert "1" in extracted or "одного" in extracted.lower()


def test_gs05_otchetnost_rp() -> None:
    q = "Кто отвечает за организацию отчётности по проекту?"
    result = _grounding().ground(
        candidates=[_HIT_OTCHETNOST],
        draft="Ответ: Руководитель проекта.",
        query=q,
    )
    assert result.ok, result
    assert "Руководитель проекта" in (result.answer_text or "")


def test_gs06_pa_accept_application_one_day() -> None:
    q = (
        "За какой срок Пресейл-архитектор обязан принять заявку в работу "
        "после назначения?"
    )
    result = _grounding().ground(
        candidates=[_HIT_PA_NEIGHBOR_66, _HIT_PA_51],
        draft=None,
        query=q,
    )
    assert result.ok, result
    assert "1" in (result.answer_text or "") or "одного" in (
        result.answer_text or ""
    ).lower()
    assert "5.1" in (result.answer_text or "")
    # Must not prefer the neighbor SS-response clause as the sole citation.
    assert result.citations[0]["chunk_id"] == "c-5.1"


def test_gs07_dbrct_create_project_not_smeta() -> None:
    q = (
        "За сколько РП создаёт проект в системе управления проектами "
        "после подписания договора в ДБРЦТ?"
    )
    result = _grounding().ground(
        candidates=[_HIT_DBRCT_102_SMETA, _HIT_DBRCT_101],
        draft=None,
        query=q,
    )
    assert result.ok, result
    body = (result.answer_text or "").lower()
    assert "1" in (result.answer_text or "") or "одного" in body
    assert result.citations[0]["chunk_id"] == "c-10.1"
    # Must not answer with the 3-day smeta deadline as the grounded quote.
    assert "3 рабочих" not in (result.citations[0].get("quote") or "")


# --- GS-08…10 clarify ---


@pytest.mark.asyncio
async def test_gs08_clarify_underspec_organization() -> None:
    graph = _graph(label="underspecified", hits=[_HIT_OTCHETNOST])
    out = await graph.ainvoke(
        {
            "user_message": "Кто отвечает за организацию?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "clarify"
    assert out.get("clarification_text")


@pytest.mark.asyncio
async def test_gs09_clarify_ambiguous_contracts() -> None:
    graph = _graph(label="ambiguous", hits=[_HIT_PURCHASE_95])
    out = await graph.ainvoke(
        {
            "user_message": "Кто подписывает договоры?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "clarify"


@pytest.mark.asyncio
async def test_gs10_clarify_presale_deadline_no_scope() -> None:
    graph = _graph(label="underspecified", hits=[_HIT_DBRCT_15, _HIT_PA_51])
    out = await graph.ainvoke(
        {
            "user_message": "Какой срок на пресейл?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "clarify"


# --- GS-11…13 escalate ---


def test_gs11_margin_percent_escalates() -> None:
    q = "Какой точный процент пороговой маржинальности установлен в Дирекции ИБ?"
    result = _grounding().ground(
        candidates=[_HIT_BUDGET_WEAK], draft=None, query=q
    )
    assert result.ok is False
    assert result.reason == "irrelevant_citations"
    assert result.answer_text is None


@pytest.mark.asyncio
async def test_gs11_margin_graph_escalates() -> None:
    graph = _graph(label="specific", hits=[_HIT_BUDGET_WEAK])
    out = await graph.ainvoke(
        {
            "user_message": (
                "Какой точный процент пороговой маржинальности "
                "установлен в Дирекции ИБ?"
            ),
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "escalate"
    assert out.get("escalation_reason") in {
        "irrelevant_citations",
        "insufficient_citations",
        "paraphrase_required",
        "ungrounded",
    }


def test_gs12_target_margin_no_number_escalates() -> None:
    q = "Чему равна целевая маржинальность услуг по регламенту Дирекции ИБ?"
    result = _grounding().ground(
        candidates=[_HIT_MARGIN_NO_NUMBER], draft=None, query=q
    )
    assert result.ok is False
    assert result.reason in {
        "irrelevant_citations",
        "paraphrase_required",
        "insufficient_citations",
    }
    assert result.answer_text is None


def test_gs13_contractor_sla_no_number_escalates() -> None:
    q = (
        "Какой точный SLA в рабочих днях на поиск и согласование подрядчика "
        "при оценке в ДБРЦТ?"
    )
    # Tempting neighbors with numeric deadlines must not become the answer.
    result = _grounding().ground(
        candidates=[_HIT_DBRCT_15, _HIT_DBRCT_17_SLA],
        draft=None,
        query=q,
    )
    assert result.ok is False
    assert result.answer_text is None


# --- GS-14…16 refuse ---


def test_gs14_weather_moscow_is_off_topic() -> None:
    assert is_off_topic("Какая сегодня погода в Москве?")


@pytest.mark.asyncio
async def test_gs14_weather_graph_refuses() -> None:
    graph = _graph(label="specific", hits=[_HIT_RP_27])
    out = await graph.ainvoke(
        {
            "user_message": "Какая сегодня погода в Москве?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "refuse"
    assert out.get("specificity") == "off_topic"


def test_gs15_borscht_is_off_topic() -> None:
    assert is_off_topic("Как приготовить борщ?")


@pytest.mark.asyncio
async def test_gs15_borscht_graph_refuses() -> None:
    graph = _graph(label="specific", hits=[])
    out = await graph.ainvoke(
        {
            "user_message": "Как приготовить борщ?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "refuse"


@pytest.mark.asyncio
async def test_gs16_constitution_regs_only_refuses() -> None:
    """Default allowlist has no Конституция → classify off_topic stays refuse."""
    graph = _graph(label="off_topic", hits=[])
    out = await graph.ainvoke(
        {
            "user_message": "Что говорит Конституция РФ о свободе слова?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "refuse"
    assert "escalate" not in (out.get("node_trace") or [])
