import uuid

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, select

from app.api.deps import CurrentUser, SessionDep
from app.api.routes.conversations import get_conversation_or_404
from app.core.config import settings
from app.models import (
    Conversation,
    Notebook,
    StudyPlan,
    StudyPlanGenerateRequest,
    StudyPlanPublic,
    StudyPlanUpdate,
    StudyTask,
    StudyTaskPublic,
    StudyTaskUpdate,
    get_datetime_utc,
)
from app.services.chat import ChatError, get_chat_provider
from app.services.provider_settings import (
    effective_chat_config,
    load_user_provider_settings,
)
from app.services.study_plans import (
    conversation_text,
    generate_study_plan,
    plan_public,
    store_generated_plan,
    validate_timezone,
)
from app.services.usage import (
    QuotaError,
    estimate_chat_reserve,
    reserve_usage,
    settle_usage,
)

router = APIRouter(tags=["study-plans"])


def get_owned_plan_or_404(
    *, session: Session, current_user: CurrentUser, plan_id: uuid.UUID
) -> StudyPlan:
    plan = session.exec(
        select(StudyPlan)
        .join(Conversation, col(StudyPlan.conversation_id) == col(Conversation.id))
        .join(Notebook, col(Conversation.notebook_id) == col(Notebook.id))
        .where(StudyPlan.id == plan_id)
        .where(Notebook.owner_id == current_user.id)
    ).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="学习计划不存在")
    return plan


@router.get(
    "/conversations/{conversation_id}/study-plan",
    response_model=StudyPlanPublic | None,
)
def read_conversation_study_plan(
    conversation_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> StudyPlanPublic | None:
    conversation = get_conversation_or_404(
        session=session, current_user=current_user, conversation_id=conversation_id
    )
    plan = session.exec(
        select(StudyPlan).where(StudyPlan.conversation_id == conversation.id)
    ).first()
    if plan is None:
        return None
    return plan_public(session=session, plan=plan, user=current_user)


@router.post(
    "/conversations/{conversation_id}/study-plan",
    response_model=StudyPlanPublic,
)
def create_or_regenerate_study_plan(
    conversation_id: uuid.UUID,
    request: StudyPlanGenerateRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> StudyPlanPublic:
    conversation = get_conversation_or_404(
        session=session, current_user=current_user, conversation_id=conversation_id
    )
    try:
        timezone = validate_timezone(request.timezone)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    context = conversation_text(session, conversation.id)
    if not context:
        raise HTTPException(
            status_code=400, detail="当前会话还没有可用于生成计划的内容"
        )
    user_settings = load_user_provider_settings(session, current_user.id)
    provider = get_chat_provider(effective_chat_config(user_settings))
    reserved = 0
    try:
        reserved, _ = reserve_usage(
            session=session,
            user_id=current_user.id,
            user_settings=user_settings,
            chat_tokens=estimate_chat_reserve(context),
        )
        generated = generate_study_plan(
            session=session,
            conversation_id=conversation.id,
            chat_provider=provider,
        )
    except QuotaError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except (ChatError, RuntimeError) as error:
        if reserved:
            settle_usage(
                session=session,
                user_id=current_user.id,
                chat_tokens=-reserved,
            )
        raise HTTPException(status_code=503, detail=str(error)) from error

    if reserved:
        settle_usage(
            session=session,
            user_id=current_user.id,
            chat_tokens=getattr(provider, "total_tokens_used", 0) - reserved,
        )
    plan = store_generated_plan(
        session=session,
        conversation=conversation,
        generated=generated,
        timezone=timezone,
    )
    return plan_public(session=session, plan=plan, user=current_user)


@router.patch("/study-plans/{plan_id}", response_model=StudyPlanPublic)
def update_study_plan(
    plan_id: uuid.UUID,
    request: StudyPlanUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> StudyPlanPublic:
    plan = get_owned_plan_or_404(
        session=session, current_user=current_user, plan_id=plan_id
    )
    update = request.model_dump(exclude_unset=True)
    if "timezone" in update:
        try:
            plan.timezone = validate_timezone(update["timezone"])
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        plan.last_reminder_date = None
    if update.get("reminder_enabled") is True:
        if not settings.emails_enabled:
            raise HTTPException(status_code=400, detail="服务器尚未配置邮件发送服务")
        if not current_user.is_email_verified:
            raise HTTPException(status_code=400, detail="请先验证邮箱再开启学习提醒")
    if "reminder_enabled" in update:
        plan.reminder_enabled = update["reminder_enabled"]
    plan.updated_at = get_datetime_utc()
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan_public(session=session, plan=plan, user=current_user)


@router.patch("/study-plans/{plan_id}/tasks/{task_id}", response_model=StudyTaskPublic)
def update_study_task(
    plan_id: uuid.UUID,
    task_id: uuid.UUID,
    request: StudyTaskUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> StudyTaskPublic:
    get_owned_plan_or_404(session=session, current_user=current_user, plan_id=plan_id)
    task = session.exec(
        select(StudyTask)
        .where(StudyTask.id == task_id)
        .where(StudyTask.plan_id == plan_id)
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="学习任务不存在")
    task.is_completed = request.is_completed
    session.add(task)
    session.commit()
    session.refresh(task)
    return StudyTaskPublic.model_validate(task)


@router.delete("/study-plans/{plan_id}")
def delete_study_plan(
    plan_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    plan = get_owned_plan_or_404(
        session=session, current_user=current_user, plan_id=plan_id
    )
    session.delete(plan)
    session.commit()
    return {"message": "学习计划已删除"}
