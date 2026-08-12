from datetime import UTC, date, datetime

import pytest
from pytest import MonkeyPatch
from sqlmodel import Session

from app.core.config import settings
from app.models import Conversation, Notebook, StudyPlan, StudyTask
from app.services.chat import ChatError
from app.services.study_plans import (
    dispatch_due_study_reminders,
    is_missing_study_plan_schema,
    parse_generated_study_plan,
)
from tests.utils.user import create_random_user


def test_missing_study_plan_schema_detects_undefined_table() -> None:
    assert is_missing_study_plan_schema(
        RuntimeError('relation "study_plan" does not exist')
    )
    assert is_missing_study_plan_schema(RuntimeError("UndefinedTable: study_plan"))
    assert is_missing_study_plan_schema(
        RuntimeError('relation "study_task" does not exist')
    )
    assert not is_missing_study_plan_schema(RuntimeError("connection refused"))
    assert not is_missing_study_plan_schema(
        RuntimeError('relation "user" does not exist')
    )


def test_parser_bounds_duration_and_fills_uncovered_days() -> None:
    generated = parse_generated_study_plan(
        {
            "title": "学习主题",
            "summary": "自动安排周期",
            "difficulty": "hard",
            "duration_days": 99,
            "tasks": [
                {
                    "title": "起步",
                    "description": "建立基础",
                    "start_day": 1,
                    "end_day": 2,
                    "estimated_minutes": 10,
                }
            ],
        }
    )

    assert generated.duration_days == 60
    assert generated.difficulty == "advanced"
    assert generated.tasks[0].estimated_minutes == 15
    assert generated.tasks[-1].start_day == 3
    assert generated.tasks[-1].end_day == 60


def test_parser_rejects_empty_title_and_tasks() -> None:
    with pytest.raises(ChatError, match="学习计划标题"):
        parse_generated_study_plan({"title": " ", "summary": "说明", "tasks": []})
    with pytest.raises(ChatError, match="可执行的学习任务"):
        parse_generated_study_plan(
            {
                "title": "计划",
                "summary": "说明",
                "duration_days": 7,
                "tasks": [{"title": "", "description": "空"}],
            }
        )


def test_scheduler_sends_once_at_local_nine(
    db: Session, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    user = create_random_user(db)
    user.is_email_verified = True
    db.add(user)
    notebook = Notebook(title="测试", owner_id=user.id)
    db.add(notebook)
    db.flush()
    conversation = Conversation(notebook_id=notebook.id, title="学习")
    db.add(conversation)
    db.flush()
    day = date(2026, 8, 4)
    plan = StudyPlan(
        conversation_id=conversation.id,
        title="七天学习计划",
        summary="循序渐进",
        difficulty="intermediate",
        start_date=day,
        end_date=day,
        timezone="Asia/Shanghai",
        reminder_enabled=True,
    )
    db.add(plan)
    db.flush()
    db.add(
        StudyTask(
            plan_id=plan.id,
            title="今日任务",
            description="完成练习并复盘",
            start_date=day,
            end_date=day,
            estimated_minutes=45,
        )
    )
    db.commit()
    sent: list[dict[str, object]] = []

    def sender(**kwargs: object) -> bool:
        sent.append(kwargs)
        return True

    now = datetime(2026, 8, 4, 1, 5, tzinfo=UTC)
    assert dispatch_due_study_reminders(session=db, now=now, sender=sender) == 1
    assert dispatch_due_study_reminders(session=db, now=now, sender=sender) == 0
    assert len(sent) == 1
    assert "今日学习计划" in str(sent[0]["subject"])
    assert f"?conversation={conversation.id}" in str(sent[0]["html_content"])


def test_scheduler_skips_opted_out_plan(db: Session, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    user = create_random_user(db)
    user.is_email_verified = True
    db.add(user)
    notebook = Notebook(title="测试", owner_id=user.id)
    db.add(notebook)
    db.flush()
    conversation = Conversation(notebook_id=notebook.id, title="学习")
    db.add(conversation)
    db.flush()
    day = date(2026, 8, 4)
    db.add(
        StudyPlan(
            conversation_id=conversation.id,
            title="不提醒",
            summary="用户没有开启提醒",
            difficulty="beginner",
            start_date=day,
            end_date=day,
            timezone="Asia/Shanghai",
            reminder_enabled=False,
        )
    )
    db.commit()

    assert (
        dispatch_due_study_reminders(
            session=db,
            now=datetime(2026, 8, 4, 1, 0, tzinfo=UTC),
            sender=lambda **_: True,
        )
        == 0
    )
