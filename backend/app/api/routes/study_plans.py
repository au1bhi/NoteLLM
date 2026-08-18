import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import ProgrammingError
from sqlmodel import Session, col, select

from app.api.deps import CurrentUser, SessionDep
from app.api.routes.conversations import get_conversation_or_404
from app.core.config import settings
from app.core.rate_limit import rate_limit
from app.models import (
    Conversation,
    Notebook,
    StudyPlan,
    StudyPlanGenerateRequest,
    StudyPlanPublic,
    StudyPlansPublic,
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
    MISSING_STUDY_PLAN_SCHEMA,
    conversation_text,
    generate_study_plan,
    is_missing_study_plan_schema,
    list_owned_plans,
    plan_public,
    store_generated_plan,
    validate_timezone,
)
from app.services.usage import (
    QuotaError,
    estimate_chat_reserve,
    usage_reservation,
)

router = APIRouter(tags=["study-plans"])


@router.get("/study-plans", response_model=StudyPlansPublic)
def read_study_plans(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
    notebook_id: uuid.UUID | None = None,
) -> StudyPlansPublic:
    try:
        items, count = list_owned_plans(
            session=session,
            user=current_user,
            skip=skip,
            limit=limit,
            notebook_id=notebook_id,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return StudyPlansPublic(data=items, count=count)


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
    try:
        plan = session.exec(
            select(StudyPlan).where(StudyPlan.conversation_id == conversation.id)
        ).first()
    except ProgrammingError as error:
        if is_missing_study_plan_schema(error):
            raise HTTPException(
                status_code=503, detail=MISSING_STUDY_PLAN_SCHEMA
            ) from error
        raise
    if plan is None:
        return None
    return plan_public(session=session, plan=plan, user=current_user)


@router.post(
    "/conversations/{conversation_id}/study-plan",
    response_model=StudyPlanPublic,
    dependencies=[Depends(rate_limit(limit=30, window=60))],
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
    try:
        with usage_reservation(
            session=session,
            user_id=current_user.id,
            user_settings=user_settings,
            chat_tokens=estimate_chat_reserve(context),
        ) as reservation:
            generated = generate_study_plan(
                session=session,
                conversation_id=conversation.id,
                chat_provider=provider,
            )
            reservation.set_actual(
                chat_tokens=getattr(provider, "total_tokens_used", 0)
            )
    except QuotaError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (ChatError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    try:
        plan = store_generated_plan(
            session=session,
            conversation=conversation,
            generated=generated,
            timezone=timezone,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
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
