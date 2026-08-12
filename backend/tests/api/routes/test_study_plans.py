import uuid
from datetime import date

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
