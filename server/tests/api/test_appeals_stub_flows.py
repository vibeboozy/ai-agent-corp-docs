"""
ANCHOR: tests.api.test_appeals_stub_flows
PURPOSE: HTTP contract tests for appeals/messages/officer-reply/stats under stubs.
Dependencies: app.main via TestClient
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_appeal_grounded_flow(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/appeals",
        json={
            "user_id": "u-1",
            "topic": "procurement",
            "message": {"content": "Кто подписывает договоры на закупку?"},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["appeal"]["status"] == "answered"
    assert body["messages"]
    answer = next(m for m in body["messages"] if m["message_kind"] == "answer")
    assert answer["citations"]

    appeal_id = body["appeal"]["id"]
    listed = client.get(f"/api/v1/appeals/{appeal_id}/messages")
    assert listed.status_code == 200
    assert listed.json()["appeal_id"] == appeal_id
    assert len(listed.json()["items"]) >= 2


def test_clarify_then_answer(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/appeals",
        json={"message": {"content": "Кто подписывает договоры?"}},
    )
    assert resp.status_code == 201
    assert resp.json()["appeal"]["status"] == "clarifying"
    appeal_id = resp.json()["appeal"]["id"]

    follow = client.post(
        f"/api/v1/appeals/{appeal_id}/messages",
        json={"content": "Это про договоры на закупку товаров."},
    )
    assert follow.status_code == 201, follow.text
    assert follow.json()["appeal"]["status"] == "answered"
    answer = next(m for m in follow.json()["messages"] if m["message_kind"] == "answer")
    assert answer["citations"]


def test_escalate_officer_learning_api(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/appeals",
        json={
            "message": {
                "content": "Какой цвет логотипа у конкурентов согласно брендбуку компании?"
            }
        },
    )
    assert resp.status_code == 201
    assert resp.json()["appeal"]["status"] == "escalated"
    appeal_id = resp.json()["appeal"]["id"]

    officer = client.post(
        f"/api/v1/appeals/{appeal_id}/officer-reply",
        json={
            "content": (
                "По брендбуку фирменный цвет логотипа — тёмно-зелёный Pantone 3435; "
                "логотипы конкурентов не используются."
            ),
            "source_document_hint": "brandbook",
        },
    )
    assert officer.status_code == 201, officer.text
    assert officer.json()["learning"]["accepted"] is True
    assert officer.json()["appeal"]["status"] == "resolved_by_officer"

    replay = client.post(
        "/api/v1/appeals",
        json={"message": {"content": "Какой цвет логотипа в брендбуке?"}},
    )
    assert replay.status_code == 201
    assert replay.json()["appeal"]["status"] == "answered"


def test_list_appeals_filter_and_stats(client: TestClient) -> None:
    client.post(
        "/api/v1/appeals",
        json={"message": {"content": "Кто подписывает договоры на закупку?"}},
    )
    client.post(
        "/api/v1/appeals",
        json={"message": {"content": "Кто подписывает договоры?"}},
    )
    listed = client.get("/api/v1/appeals", params={"status": "answered"})
    assert listed.status_code == 200
    body = listed.json()
    assert "items" in body and "total" in body
    assert all(i["status"] == "answered" for i in body["items"])

    stats = client.get("/api/v1/stats")
    assert stats.status_code == 200
    s = stats.json()
    assert s["appeals_total"] >= 2
    assert "by_status" in s
    assert "clarify_rate" in s
