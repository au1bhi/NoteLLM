import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlmodel import Session

from app.core.config import settings
from app.models import Conversation, ConversationMessage, StudyPlan, StudyTask, User
from tests.utils.notebook import create_random_notebook
from tests.utils.user import authentication_token_from_email, create_random_user


class FakePlanProvider:
    total_tokens_used = 100

    def complete_json(
        self, *, prompt: str, system: str | None = None
    ) -> dict[str, object]:
        assert "学习对话" in prompt
        assert system
        return {
            "title": "RAG 学习冲刺",
            "summary": "内容具有一定综合性，安排七天完成理解与实践。",
            "difficulty": "intermediate",
            "duration_days": 7,
            "tasks": [
                {
                    "title": "理解检索流程",
                    "description": "梳理检索链路并画出流程图。",
                    "start_day": 1,
                    "end_day": 3,
                    "estimated_minutes": 45,
                },
                {
                    "title": "实现与验收",
                    "description": "完成一个可运行示例并记录结果。",
                    "start_day": 4,
                    "end_day": 7,
                    "estimated_minutes": 60,
                },
            ],
        }


def _conversation_with_message(db: Session) -> tuple[User, Conversation]:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    conversation = Conversation(notebook_id=notebook.id, title="RAG 学习")
    db.add(conversation)
    db.flush()
    db.add(
        ConversationMessage(
            conversation_id=conversation.id,
            role="user",
            content="我想系统学习 RAG，并做出一个可验证引用的问答系统。",
        )
    )
    db.commit()
    db.refresh(conversation)
    return user, conversation


def test_generate_read_and_update_study_plan(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    user, conversation = _conversation_with_message(db)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    monkeypatch.setattr(
        "app.api.routes.study_plans.get_chat_provider",
        lambda _config: FakePlanProvider(),
    )

    empty = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation.id}/study-plan",
        headers=headers,
    )
    assert empty.status_code == 200
    assert empty.json() is None

    generated = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation.id}/study-plan",
        headers=headers,
        json={"timezone": "Asia/Shanghai"},
    )
    assert generated.status_code == 200, generated.text
    plan = generated.json()
    assert plan["title"] == "RAG 学习冲刺"
    assert plan["difficulty"] == "intermediate"
    assert plan["reminder_enabled"] is False
    assert plan["reminder_time"] == "09:00"
    assert len(plan["tasks"]) == 2

    updated = client.patch(
        f"{settings.API_V1_STR}/study-plans/{plan['id']}/tasks/{plan['tasks'][0]['id']}",
        headers=headers,
        json={"is_completed": True},
    )
    assert updated.status_code == 200
    assert updated.json()["is_completed"] is True


def test_reminder_requires_verified_email(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    user, conversation = _conversation_with_message(db)
    plan = StudyPlan(
        conversation_id=conversation.id,
        title="计划",
        summary="说明",
        difficulty="beginner",
        start_date=date.today(),
        end_date=date.today(),
        timezone="Asia/Shanghai",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")

    denied = client.patch(
        f"{settings.API_V1_STR}/study-plans/{plan.id}",
        headers=headers,
        json={"reminder_enabled": True},
    )
    assert denied.status_code == 400
    assert "验证邮箱" in denied.json()["detail"]

    db.refresh(user)
    user.is_email_verified = True
    db.add(user)
    db.commit()
    allowed = client.patch(
        f"{settings.API_V1_STR}/study-plans/{plan.id}",
        headers=headers,
        json={"reminder_enabled": True},
    )
    assert allowed.status_code == 200
    assert allowed.json()["reminder_enabled"] is True
    assert allowed.json()["email_reminder_available"] is True


def test_user_cannot_access_another_users_study_plan(
    client: TestClient, db: Session
) -> None:
    _owner, conversation = _conversation_with_message(db)
    plan = StudyPlan(
        conversation_id=conversation.id,
        title="私有计划",
        summary="私有",
        difficulty="advanced",
        start_date=date.today(),
        end_date=date.today(),
        timezone="Asia/Shanghai",
    )
    db.add(plan)
    db.commit()
    other = create_random_user(db)
    headers = authentication_token_from_email(client=client, email=other.email, db=db)

    response = client.patch(
        f"{settings.API_V1_STR}/study-plans/{plan.id}",
        headers=headers,
        json={"reminder_enabled": False},
    )
    assert response.status_code == 404


def _add_plan(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    title: str,
    start: date,
    end: date,
    task_title: str,
) -> StudyPlan:
    plan = StudyPlan(
        conversation_id=conversation_id,
        title=title,
        summary="说明",
        difficulty="beginner",
        start_date=start,
        end_date=end,
        timezone="Asia/Shanghai",
    )
    db.add(plan)
    db.flush()
    db.add(
        StudyTask(
            plan_id=plan.id,
            title=task_title,
            description="完成练习",
            start_date=start,
            end_date=end,
            estimated_minutes=45,
        )
    )
    db.commit()
    db.refresh(plan)
    return plan


def test_list_study_plans_aggregates_owned_conversations(
    client: TestClient, db: Session
) -> None:
    user = create_random_user(db)
    first_notebook = create_random_notebook(db=db, owner_id=user.id)
    second_notebook = create_random_notebook(db=db, owner_id=user.id)
    first = Conversation(notebook_id=first_notebook.id, title="检索对话")
    second = Conversation(notebook_id=second_notebook.id, title="引用对话")
    db.add(first)
    db.add(second)
    db.flush()
    today = date.today()
    _add_plan(
        db,
        conversation_id=first.id,
        title="检索计划",
        start=today,
        end=today,
        task_title="梳理检索",
    )
    _add_plan(
        db,
        conversation_id=second.id,
        title="引用计划",
        start=today,
        end=today,
        task_title="核对引用",
    )

    other_user, other_conversation = _conversation_with_message(db)
    _add_plan(
        db,
        conversation_id=other_conversation.id,
        title="他人计划",
        start=today,
        end=today,
        task_title="不该出现",
    )

    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    listed = client.get(f"{settings.API_V1_STR}/study-plans", headers=headers)
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["count"] == 2
    titles = {item["title"] for item in payload["data"]}
    assert titles == {"检索计划", "引用计划"}
    first_item = next(item for item in payload["data"] if item["title"] == "检索计划")
    assert first_item["notebook_id"] == str(first_notebook.id)
    assert first_item["notebook_title"] == first_notebook.title
    assert first_item["conversation_id"] == str(first.id)
    assert first_item["conversation_title"] == "检索对话"
    assert first_item["tasks"][0]["title"] == "梳理检索"

    filtered = client.get(
        f"{settings.API_V1_STR}/study-plans",
        headers=headers,
        params={"notebook_id": str(second_notebook.id)},
    )
    assert filtered.status_code == 200
    assert filtered.json()["count"] == 1
    assert filtered.json()["data"][0]["title"] == "引用计划"

    hidden = client.get(
        f"{settings.API_V1_STR}/study-plans",
        headers=headers,
        params={"notebook_id": str(other_conversation.notebook_id)},
    )
    assert hidden.status_code == 200
    assert hidden.json() == {"data": [], "count": 0}

    empty = client.get(
        f"{settings.API_V1_STR}/study-plans",
        headers=authentication_token_from_email(
            client=client, email=create_random_user(db).email, db=db
        ),
    )
    assert empty.status_code == 200
    assert empty.json() == {"data": [], "count": 0}

    stranger = authentication_token_from_email(
        client=client, email=other_user.email, db=db
    )
    other_listed = client.get(f"{settings.API_V1_STR}/study-plans", headers=stranger)
    assert {item["title"] for item in other_listed.json()["data"]} == {"他人计划"}


def test_list_study_plans_reports_uninitialized_schema(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    user = create_random_user(db)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    monkeypatch.setattr(
        "app.api.routes.study_plans.list_owned_plans",
        lambda **_: (_ for _ in ()).throw(
            RuntimeError(
                "学习计划数据表尚未初始化，请先在 backend 目录运行 alembic upgrade head"
            )
        ),
    )
    response = client.get(f"{settings.API_V1_STR}/study-plans", headers=headers)
    assert response.status_code == 503
    assert "alembic upgrade head" in response.json()["detail"]


def test_generate_study_plan_reports_uninitialized_schema(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    user, conversation = _conversation_with_message(db)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    monkeypatch.setattr(
        "app.api.routes.study_plans.get_chat_provider",
        lambda _config: FakePlanProvider(),
    )
    monkeypatch.setattr(
        "app.api.routes.study_plans.store_generated_plan",
        lambda **_: (_ for _ in ()).throw(
            RuntimeError(
                "学习计划数据表尚未初始化，请先在 backend 目录运行 alembic upgrade head"
            )
        ),
    )
    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation.id}/study-plan",
        headers=headers,
        json={"timezone": "Asia/Shanghai"},
    )
    assert response.status_code == 503
    assert "alembic upgrade head" in response.json()["detail"]


def test_generate_study_plan_rejects_empty_conversation(
    client: TestClient, db: Session
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    conversation = Conversation(notebook_id=notebook.id, title="空会话")
    db.add(conversation)
    db.commit()
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation.id}/study-plan",
        headers=headers,
        json={"timezone": "Asia/Shanghai"},
    )
    assert response.status_code == 400
    assert "还没有可用于生成计划的内容" in response.json()["detail"]


def test_generate_study_plan_reports_unconfigured_chat(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    from app.services.chat import ChatError

    user, conversation = _conversation_with_message(db)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)

    class UnconfiguredProvider:
        total_tokens_used = 0

        def complete_json(
            self, *, prompt: str, system: str | None = None
        ) -> dict[str, object]:
            raise ChatError(
                "对话模型尚未配置。请在设置中填写 API Key，或由管理员配置服务端模型。"
            )

    monkeypatch.setattr(
        "app.api.routes.study_plans.get_chat_provider",
        lambda _config: UnconfiguredProvider(),
    )
    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation.id}/study-plan",
        headers=headers,
        json={"timezone": "Asia/Shanghai"},
    )
    assert response.status_code == 503
    assert "对话模型尚未配置" in response.json()["detail"]


def test_cross_user_study_plan_security_isolation(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    user1, conversation1 = _conversation_with_message(db)
    headers1 = authentication_token_from_email(
        client=client, email=user1.email, db=db
    )
    user2 = create_random_user(db)
    headers2 = authentication_token_from_email(
        client=client, email=user2.email, db=db
    )

    monkeypatch.setattr(
        "app.api.routes.study_plans.get_chat_provider",
        lambda _config: FakePlanProvider(),
    )

    # User 1 generates a study plan
    resp = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation1.id}/study-plan",
        headers=headers1,
        json={"timezone": "Asia/Shanghai"},
    )
    assert resp.status_code == 200
    plan_id = resp.json()["id"]
    task_id = resp.json()["tasks"][0]["id"]

    # User 2 attempts to read User 1's conversation plan -> 404 (conversation not found)
    r = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation1.id}/study-plan",
        headers=headers2,
    )
    assert r.status_code == 404

    # User 2 attempts to generate a plan for User 1's conversation -> 404
    r = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation1.id}/study-plan",
        headers=headers2,
        json={"timezone": "Asia/Shanghai"},
    )
    assert r.status_code == 404

    # User 2 attempts to patch User 1's plan -> 404
    r = client.patch(
        f"{settings.API_V1_STR}/study-plans/{plan_id}",
        headers=headers2,
        json={"title": "Hacked Title"},
    )
    assert r.status_code == 404

    # User 2 attempts to patch User 1's task -> 404
    r = client.patch(
        f"{settings.API_V1_STR}/study-plans/{plan_id}/tasks/{task_id}",
        headers=headers2,
        json={"title": "Hacked Task"},
    )
    assert r.status_code == 404

    # User 2 attempts to delete User 1's task -> 404
    r = client.delete(
        f"{settings.API_V1_STR}/study-plans/{plan_id}/tasks/{task_id}",
        headers=headers2,
    )
    assert r.status_code == 404

    # User 2 attempts to delete User 1's plan -> 404
    r = client.delete(
        f"{settings.API_V1_STR}/study-plans/{plan_id}",
        headers=headers2,
    )
    assert r.status_code == 404

    # User 2 lists plans -> does not see User 1's plan
    r = client.get(
        f"{settings.API_V1_STR}/study-plans",
        headers=headers2,
    )
    assert r.status_code == 200
    assert len(r.json()["data"]) == 0



def test_read_conversation_plan_none_then_present(
    client: TestClient, db: Session
) -> None:
    user, conversation = _conversation_with_message(db)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    url = f"{settings.API_V1_STR}/conversations/{conversation.id}/study-plan"
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json() is None

    plan = _add_plan(
        db,
        conversation_id=conversation.id,
        title="冲刺计划",
        start=date(2026, 9, 1),
        end=date(2026, 9, 7),
        task_title="读材料",
    )
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(plan.id)
    assert body["title"] == "冲刺计划"
    assert body["tasks"], "tasks should be embedded in the detail payload"


def test_read_conversation_plan_maps_missing_schema(
    monkeypatch: MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock

    from fastapi import HTTPException
    from sqlalchemy.exc import ProgrammingError

    from app.api.routes.study_plans import read_conversation_study_plan

    conversation_stub = MagicMock()
    conversation_stub.id = uuid.uuid4()
    monkeypatch.setattr(
        "app.api.routes.study_plans.get_conversation_or_404",
        lambda **_: conversation_stub,
    )
    broken_session = MagicMock()
    broken_session.exec.side_effect = ProgrammingError(
        'relation "study_plan" does not exist', None, Exception("42P01")
    )
    with pytest.raises(HTTPException) as captured:
        read_conversation_study_plan(
            conversation_id=uuid.uuid4(),
            session=broken_session,
            current_user=MagicMock(),
        )
    assert captured.value.status_code == 503


def test_create_rejects_invalid_timezone(client: TestClient, db: Session) -> None:
    user, conversation = _conversation_with_message(db)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation.id}/study-plan",
        headers=headers,
        json={"timezone": "Mars/Olympus"},
    )
    assert response.status_code == 422


def test_create_maps_quota_and_value_errors(
    client: TestClient,
    db: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    user, conversation = _conversation_with_message(db)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    url = f"{settings.API_V1_STR}/conversations/{conversation.id}/study-plan"

    from contextlib import contextmanager

    from app.services.usage import QuotaError, usage_reservation

    @contextmanager
    def quota_blocked(**_kwargs):
        raise QuotaError("本月的免费对话额度已用完（测试）")
        yield

    monkeypatch.setattr(
        "app.api.routes.study_plans.usage_reservation", quota_blocked
    )
    response = client.post(url, headers=headers, json={"timezone": "Asia/Shanghai"})
    assert response.status_code == 429
    assert "测试" in response.json()["detail"]

    # Restore the real reservation so only generate_study_plan fails next.
    monkeypatch.setattr(
        "app.api.routes.study_plans.usage_reservation", usage_reservation
    )

    def bad_payload(**_kwargs):
        raise ValueError("模型返回的计划缺少字段")

    monkeypatch.setattr(
        "app.api.routes.study_plans.generate_study_plan", bad_payload
    )
    monkeypatch.setattr(
        "app.api.routes.study_plans.get_chat_provider",
        lambda _config: FakePlanProvider(),
    )
    response = client.post(url, headers=headers, json={"timezone": "Asia/Shanghai"})
    assert response.status_code == 400
    assert "计划" in response.json()["detail"]


def _adjust_url(plan_id: uuid.UUID) -> str:
    return f"{settings.API_V1_STR}/study-plans/{plan_id}/ai-adjust"


def test_ai_adjust_plan_regenerates_tasks(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    user, conversation = _conversation_with_message(db)
    plan = _add_plan(
        db,
        conversation_id=conversation.id,
        title="旧标题",
        start=date(2026, 9, 1),
        end=date(2026, 9, 7),
        task_title="旧任务",
    )
    headers = authentication_token_from_email(client=client, email=user.email, db=db)

    seen_instructions: list[str] = []
    provider = FakePlanProvider()

    original_complete = provider.complete_json

    def capture(*, prompt: str, system: str | None = None):
        seen_instructions.append(prompt)
        return original_complete(prompt=prompt, system=system)

    provider.complete_json = capture  # type: ignore[method-assign]
    monkeypatch.setattr(
        "app.api.routes.study_plans.get_chat_provider", lambda _config: provider
    )

    response = client.post(
        _adjust_url(plan.id),
        headers=headers,
        json={"instruction": "改为只覆盖前三天，加大每日强度", "timezone": "UTC"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert any("前三天" in prompt for prompt in seen_instructions)
    # store_generated_plan replaced the old task set on the SAME plan row.
    assert [t["title"] for t in body["tasks"]] == ["理解检索流程", "实现与验收"]
    assert body["timezone"] == "UTC"


def test_ai_adjust_plan_validations(
    client: TestClient, db: Session
) -> None:
    user, conversation = _conversation_with_message(db)
    plan = _add_plan(
        db,
        conversation_id=conversation.id,
        title="p",
        start=date(2026, 9, 1),
        end=date(2026, 9, 2),
        task_title="t",
    )
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    base = {"instruction": "压缩一下"}

    response = client.post(
        _adjust_url(plan.id), headers=headers, json={**base, "timezone": "Nope/X"}
    )
    assert response.status_code == 422

    response = client.post(
        _adjust_url(plan.id),
        headers=headers,
        json={"instruction": "   ", "timezone": "UTC"},
    )
    assert response.status_code == 400
    assert "调整要求" in response.json()["detail"]

    other_user = create_random_user(db)
    other_headers = authentication_token_from_email(
        client=client, email=other_user.email, db=db
    )
    response = client.post(
        _adjust_url(plan.id), headers=other_headers, json={**base, "timezone": "UTC"}
    )
    assert response.status_code == 404


def test_task_crud_lifecycle_and_bounds(
    client: TestClient, db: Session
) -> None:
    user, conversation = _conversation_with_message(db)
    plan = _add_plan(
        db,
        conversation_id=conversation.id,
        title="c",
        start=date(2026, 9, 1),
        end=date(2026, 9, 5),
        task_title="existing",
    )
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    tasks_url = f"{settings.API_V1_STR}/study-plans/{plan.id}/tasks"

    response = client.post(
        tasks_url,
        headers=headers,
        json={
            "title": "bad range",
            "start_date": "2026-09-09",
            "end_date": "2026-09-08",
        },
    )
    assert response.status_code == 422
    assert "结束日期" in response.json()["detail"]

    response = client.post(
        tasks_url,
        headers=headers,
        json={
            "title": "  完成实验  ",
            "start_date": "2026-08-30",
            "end_date": "2026-09-10",
            "estimated_minutes": 90,
        },
    )
    assert response.status_code == 200
    created = response.json()
    assert created["title"] == "完成实验"
    assert created["estimated_minutes"] == 90

    db.expire_all()
    refreshed = db.get(StudyPlan, plan.id)
    assert refreshed is not None
    # Bounds grew to cover the new task.
    assert str(refreshed.start_date) == "2026-08-30"
    assert str(refreshed.end_date) == "2026-09-10"

    task_id = created["id"]
    task_url = f"{tasks_url}/{task_id}"

    response = client.patch(task_url, headers=headers, json={"title": "   "})
    assert response.status_code == 422

    response = client.patch(
        task_url,
        headers=headers,
        json={"is_completed": True, "description": "已验收"},
    )
    assert response.status_code == 200
    assert response.json()["is_completed"] is True

    response = client.patch(
        task_url,
        headers=headers,
        json={"start_date": "2026-09-20", "end_date": "2026-09-19"},
    )
    assert response.status_code == 422

    response = client.patch(f"{tasks_url}/{uuid.uuid4()}", headers=headers, json={})
    assert response.status_code == 404

    # Deleting one of two tasks re-computes bounds from the survivor.
    response = client.delete(task_url, headers=headers)
    assert response.status_code == 200
    db.expire_all()
    refreshed = db.get(StudyPlan, plan.id)
    assert refreshed is not None
    assert str(refreshed.end_date) != "2026-09-10"


def test_delete_plan_removes_row(client: TestClient, db: Session) -> None:
    user, conversation = _conversation_with_message(db)
    plan = _add_plan(
        db,
        conversation_id=conversation.id,
        title="gone",
        start=date(2026, 9, 1),
        end=date(2026, 9, 2),
        task_title="t",
    )
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    url = f"{settings.API_V1_STR}/study-plans/{plan.id}"
    response = client.delete(url, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"message": "学习计划已删除"}


def test_update_plan_edit_branches(client: TestClient, db: Session) -> None:
    user, conversation = _conversation_with_message(db)
    plan = _add_plan(
        db,
        conversation_id=conversation.id,
        title="原始",
        start=date(2026, 9, 1),
        end=date(2026, 9, 3),
        task_title="t",
    )
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    url = f"{settings.API_V1_STR}/study-plans/{plan.id}"
    assert settings.emails_enabled is False  # precondition for the 400 branch

    response = client.patch(url, headers=headers, json={"title": "   "})
    assert response.status_code == 422
    assert "计划标题" in response.json()["detail"]

    response = client.patch(
        url, headers=headers, json={"summary": "新的总结", "reminder_enabled": True}
    )
    assert response.status_code == 400  # emails disabled on the test server
    assert "邮件发送服务" in response.json()["detail"]

    response = client.patch(
        url, headers=headers, json={"timezone": "Europe/Berlin", "summary": "第二次"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Europe/Berlin"
    assert body["summary"] == "第二次"
