from datetime import date

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlmodel import Session

from app.core.config import settings
from app.models import StudyPlan, StudyTask
from app.services.answers import GroundedAnswer
from tests.utils.notebook import create_random_notebook
from tests.utils.user import authentication_token_from_email, create_random_user


def test_create_list_and_read_conversation(
    client: TestClient,
    db: Session,
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)

    created = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
        json={"title": "Grounded notes"},
    )
    assert created.status_code == 200
    conversation = created.json()

    listed = client.get(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
    )
    assert listed.status_code == 200
    assert conversation["id"] in {item["id"] for item in listed.json()["data"]}

    detail = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}", headers=headers
    )
    assert detail.status_code == 200
    assert detail.json()["messages"] == []


def test_user_cannot_read_another_users_conversation(
    client: TestClient,
    db: Session,
) -> None:
    owner = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=owner.id)
    owner_headers = authentication_token_from_email(
        client=client, email=owner.email, db=db
    )
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=owner_headers,
        json={},
    ).json()
    other_user = create_random_user(db)
    other_headers = authentication_token_from_email(
        client=client, email=other_user.email, db=db
    )

    response = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}",
        headers=other_headers,
    )
    assert response.status_code == 404


def test_message_stream_emits_delta_citations_and_done(
    client: TestClient,
    db: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
        json={},
    ).json()
    monkeypatch.setattr(
        "app.api.routes.conversations.persist_answer",
        lambda **_: GroundedAnswer(content="Grounded answer", citations=[]),
    )

    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}/messages/stream",
        headers=headers,
        json={"content": "What do the notes say?"},
    )

    assert response.status_code == 200
    assert "event: delta" in response.text
    assert "event: citations" in response.text
    assert "event: done" in response.text


def test_message_stream_chunks_chinese_content(
    client: TestClient,
    db: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
        json={},
    ).json()
    monkeypatch.setattr(
        "app.api.routes.conversations.persist_answer",
        lambda **_: GroundedAnswer(content="资料不足，无法回答。", citations=[]),
    )

    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}/messages/stream",
        headers=headers,
        json={"content": "笔记里写了什么？"},
    )

    assert response.status_code == 200
    # Chinese text has no spaces, so a space-split would emit one giant delta.
    # Each CJK character must stream as its own small chunk instead. SSE
    # escapes non-ASCII as \uXXXX, so 资料不足 streams as 8 separate deltas.
    delta_events = response.text.count("event: delta")
    assert delta_events == len("资料不足，无法回答。")
    assert "\\u8d44" in response.text  # 资


def test_message_stream_forwards_answer_mode(
    client: TestClient,
    db: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
        json={},
    ).json()
    captured: dict[str, object] = {}

    def fake_persist(**kwargs: object) -> GroundedAnswer:
        captured.update(kwargs)
        return GroundedAnswer(content="Hybrid answer", citations=[])

    monkeypatch.setattr("app.api.routes.conversations.persist_answer", fake_persist)

    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}/messages/stream",
        headers=headers,
        json={"content": "Explain it", "mode": "hybrid"},
    )

    assert response.status_code == 200
    assert captured.get("mode") == "hybrid"


def test_update_conversation_title(
    client: TestClient,
    db: Session,
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
        json={},
    ).json()

    renamed = client.patch(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}",
        headers=headers,
        json={"title": "Renamed notes"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed notes"

    detail = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}", headers=headers
    )
    assert detail.json()["title"] == "Renamed notes"


def test_user_cannot_rename_another_users_conversation(
    client: TestClient,
    db: Session,
) -> None:
    owner = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=owner.id)
    owner_headers = authentication_token_from_email(
        client=client, email=owner.email, db=db
    )
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=owner_headers,
        json={},
    ).json()
    other_user = create_random_user(db)
    other_headers = authentication_token_from_email(
        client=client, email=other_user.email, db=db
    )

    response = client.patch(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}",
        headers=other_headers,
        json={"title": "Nope"},
    )
    assert response.status_code == 404


def test_pin_conversation(client: TestClient, db: Session) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
        json={},
    ).json()

    pinned = client.patch(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}",
        headers=headers,
        json={"is_pinned": True},
    )
    assert pinned.status_code == 200
    assert pinned.json()["is_pinned"] is True

    listed = client.get(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
    )
    assert listed.json()["data"][0]["is_pinned"] is True


def test_delete_conversation(client: TestClient, db: Session) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
        json={"title": "Delete me"},
    ).json()

    deleted = client.delete(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert deleted.json()["message"] == "会话删除成功"

    detail = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}", headers=headers
    )
    assert detail.status_code == 404

    listed = client.get(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
    )
    assert listed.json()["data"] == []


def test_delete_conversation_cascades_study_plan_and_tasks(
    client: TestClient, db: Session
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
        json={"title": "有计划的会话"},
    ).json()
    plan = StudyPlan(
        conversation_id=conversation["id"],
        title="学习计划",
        summary="验证删除级联",
        difficulty="beginner",
        start_date=date.today(),
        end_date=date.today(),
        timezone="Asia/Shanghai",
    )
    db.add(plan)
    db.flush()
    db.add(
        StudyTask(
            plan_id=plan.id,
            title="任务",
            description="完成验证",
            start_date=date.today(),
            end_date=date.today(),
        )
    )
    db.commit()
    plan_id = plan.id

    deleted = client.delete(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}",
        headers=headers,
    )

    assert deleted.status_code == 200, deleted.text
    db.expire_all()
    assert db.get(StudyPlan, plan_id) is None


def test_user_cannot_delete_another_users_conversation(
    client: TestClient, db: Session
) -> None:
    owner = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=owner.id)
    owner_headers = authentication_token_from_email(
        client=client, email=owner.email, db=db
    )
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=owner_headers,
        json={},
    ).json()
    other_user = create_random_user(db)
    other_headers = authentication_token_from_email(
        client=client, email=other_user.email, db=db
    )

    response = client.delete(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}",
        headers=other_headers,
    )
    assert response.status_code == 404


def test_user_cannot_stream_another_users_conversation(
    client: TestClient, db: Session
) -> None:
    owner = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=owner.id)
    owner_headers = authentication_token_from_email(
        client=client, email=owner.email, db=db
    )
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=owner_headers,
        json={},
    ).json()
    other_user = create_random_user(db)
    other_headers = authentication_token_from_email(
        client=client, email=other_user.email, db=db
    )

    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}/messages/stream",
        headers=other_headers,
        json={"content": "hi"},
    )
    assert response.status_code == 404
