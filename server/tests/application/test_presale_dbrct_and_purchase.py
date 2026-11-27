"""
ANCHOR: tests.application.test_presale_dbrct_and_purchase
PURPOSE: DBRCT пресейл lead-time + purchase-signer must not lose to junk chunks.
Dependencies: GroundingService; answer_format; corpus п.1.5 / п.9.5
Bugs:
- «За сколько рабочих дней… заявку на пресейл ДБРЦТ?» → paraphrase_required
  (should answer ~3 working days from «Проектная деятельность ДБРЦТ» п.1.5).
- «Кто подписывает договоры на закупку?» → checklist junk
  «1. подписан договор на услуги с заказчиком» (should be Юридические лица… п.9.5).
"""

from __future__ import annotations

from app.application.dialogue.answer_format import (
    extract_short_paraphrase,
    enforce_short_paraphrase,
)
from app.application.grounding.service import GroundingService
from app.domain.glossary import AbbreviationGlossary


_DBRCT_Q = "За сколько рабочих дней необходимо инициировать заявку на пресейл ДБРЦТ?"
_DBRCT_CLAUSE = (
    "1.5. Заявка должна быть инициирована не менее чем за 3 рабочих дня "
    "до подачи предложения Заказчику. При невыполнении сроков Заявка отклоняется "
    "или выполняются работы со стороны SS и АМ по продлению сроков выдачи."
)

_PURCHASE_Q = "Кто подписывает договоры на закупку?"
_PURCHASE_CLAUSE = (
    "9.5. Все субподрядные договоры по ИБ проектам, кроме перепродажи "
    "вендорских сервисов, заключаются от юридических лиц Компании."
)
_JUNK_CHECKLIST = "1. подписан договор на услуги с заказчиком"


def test_dbrct_when_extract_three_working_days() -> None:
    got = extract_short_paraphrase(_DBRCT_Q, _DBRCT_CLAUSE)
    assert "3" in got
    assert "рабоч" in got.lower()
    assert got.lower().startswith("не менее")


def test_ground_dbrct_presale_lead_time_without_draft() -> None:
    svc = GroundingService(
        min_citations=1,
        min_score=0.25,
        min_query_overlap=0.12,
        glossary=AbbreviationGlossary.from_defaults(),
    )
    result = svc.ground(
        candidates=[
            {
                "document_id": "dbrct",
                "chunk_id": "c15",
                "text": _DBRCT_CLAUSE,
                "score": 0.55,
                "document_title": "Проектная деятельность ДБРЦТ",
                "locator": "1.5.",
            }
        ],
        draft=None,
        query=_DBRCT_Q,
    )
    assert result.ok is True, result
    assert result.answer_text
    first = result.answer_text.splitlines()[0]
    assert "3" in first
    assert "рабоч" in first.lower()
    assert "1.5" in result.answer_text


def test_ground_dbrct_prefers_15_over_presale_wait_timeout_neighbors() -> None:
    """Kirill GS-01: DBRCT 1.5 must win over Presale IB 3.4/6.9 wait/timeout hits."""
    svc = GroundingService(
        min_citations=1,
        min_score=0.25,
        min_query_overlap=0.12,
        glossary=AbbreviationGlossary.from_defaults(),
    )
    wait_34 = (
        "3.4. Если от Автора заявки в течение 3 рабочих дней с момента создания "
        "Заявки информация не поступает, то Сотрудник 1 линии закрывает Заявку "
        "со статусом «Дисквалифицировано». На этом процесс пресейла прерывается."
    )
    wait_69 = (
        "6.9. Если заявка не обновлялась более 1 рабочего дня, но не более "
        "3 рабочих дней, Сотрудник 1 линии ежедневно звонит SS. Если заявка не "
        "обновлялась более 3 рабочих дней, закрывает её как неактуальную "
        "(Дисквалифицировано)."
    )
    result = svc.ground(
        candidates=[
            {
                "document_id": "presale",
                "chunk_id": "c34",
                "text": wait_34,
                "score": 0.45,
                "document_title": "Пресейловая деятельность Дирекции ИБ",
                "locator": "3.4.",
            },
            {
                "document_id": "presale",
                "chunk_id": "c69",
                "text": wait_69,
                "score": 0.42,
                "document_title": "Пресейловая деятельность Дирекции ИБ",
                "locator": "6.9.",
            },
            {
                "document_id": "dbrct",
                "chunk_id": "c15",
                "text": _DBRCT_CLAUSE,
                "score": 0.327,
                "document_title": "Проектная деятельность ДБРЦТ",
                "locator": "1.5.",
            },
        ],
        draft=None,
        query=_DBRCT_Q,
    )
    assert result.ok is True, result
    assert result.citations[0]["chunk_id"] == "c15"
    assert result.citations[0]["locator"] == "1.5"
    first = (result.answer_text or "").splitlines()[0]
    body = first.split(":", 1)[-1].strip().lower()
    assert "3" in body and "рабоч" in body
    assert body.startswith("не менее")


def test_purchase_signer_prefers_clause_95_over_checklist_junk() -> None:
    svc = GroundingService(
        min_citations=1, min_score=0.25, min_query_overlap=0.12
    )
    result = svc.ground(
        candidates=[
            {
                "document_id": "dib-project",
                "chunk_id": "junk-91",
                "text": _JUNK_CHECKLIST,
                "score": 0.69,
                "document_title": "Проектная деятельность Дирекции ИБ",
                "locator": "9.1.",
            },
            {
                "document_id": "presale",
                "chunk_id": "c95",
                "text": _PURCHASE_CLAUSE,
                "score": 0.40,
                "document_title": "Пресейловая деятельность Дирекции ИБ",
                "locator": "9.5.",
            },
        ],
        draft="Ответ: Подписан договор на услуги с заказчиком.",
        query=_PURCHASE_Q,
    )
    assert result.ok is True, result
    first = (result.answer_text or "").splitlines()[0]
    assert "Юридические лица Компании" in first
    assert "подписан договор на услуги" not in first.lower()
    assert result.citations[0]["chunk_id"] == "c95"
    assert result.citations[0]["locator"] == "9.5"


def test_purchase_junk_alone_escalates() -> None:
    svc = GroundingService(
        min_citations=1, min_score=0.0, min_query_overlap=0.12
    )
    result = svc.ground(
        candidates=[
            {
                "document_id": "dib",
                "chunk_id": "junk",
                "text": _JUNK_CHECKLIST,
                "score": 0.9,
                "document_title": "Проектная деятельность Дирекции ИБ",
                "locator": "9.1.",
            }
        ],
        draft="Ответ: Подписан договор на услуги с заказчиком.",
        query=_PURCHASE_Q,
    )
    assert result.ok is False
    assert result.reason in {"irrelevant_citations", "insufficient_citations", "paraphrase_required"}
    assert result.answer_text is None


def test_enforce_rejects_checklist_as_who_answer() -> None:
    got = enforce_short_paraphrase(
        _JUNK_CHECKLIST, query=_PURCHASE_Q, quote=_JUNK_CHECKLIST
    )
    assert got == ""


def test_purchase_signer_prefers_95_over_ds_am_signing() -> None:
    """Kirill GS-02: not АМ/20.7 DS signing — юр. лица / п. 9.5."""
    ds_am = (
        "20.7. Любые изменения условий проекта оформляются Дополнительным "
        "соглашением (ДС) к договору с Заказчиком. АМ/Менеджер по продаже "
        "решений подписывает ДС с заказчиком."
    )
    svc = GroundingService(min_citations=1, min_score=0.25, min_query_overlap=0.12)
    result = svc.ground(
        candidates=[
            {
                "document_id": "tech",
                "chunk_id": "c207",
                "text": ds_am,
                "score": 0.55,
                "document_title": "Организация проектной деятельности",
                "locator": "20.7.",
            },
            {
                "document_id": "presale",
                "chunk_id": "c95",
                "text": _PURCHASE_CLAUSE,
                "score": 0.40,
                "document_title": "Пресейловая деятельность Дирекции ИБ",
                "locator": "9.5.",
            },
        ],
        draft=None,
        query=_PURCHASE_Q,
    )
    assert result.ok is True, result
    first = (result.answer_text or "").splitlines()[0]
    assert "Юридические лица Компании" in first
    assert "АМ" not in first and "ДС" not in first
    assert result.citations[0]["chunk_id"] == "c95"
    assert result.citations[0]["locator"] == "9.5"
