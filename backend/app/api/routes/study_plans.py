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
    StudyPlanAiAdjustRequest,
    StudyPlanGenerateRequest,
    StudyPlanPublic,
    StudyPlansPublic,
    StudyPlanUpdate,
    StudyTask,
    StudyTaskCreate,
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
    adjust_study_plan,
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
    if "title" in update and update["title"] is not None:
        title = update["title"].strip()
        if not title:
            raise HTTPException(status_code=422, detail="计划标题不能为空")
        plan.title = title
    if "summary" in update and update["summary"] is not None:
        plan.summary = update["summary"]
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


@router.post(
    "/study-plans/{plan_id}/ai-adjust",
    response_model=StudyPlanPublic,
    dependencies=[Depends(rate_limit(limit=30, window=60))],
)
def ai_adjust_plan(
    plan_id: uuid.UUID,
    request: StudyPlanAiAdjustRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> StudyPlanPublic:
    plan = get_owned_plan_or_404(
        session=session, current_user=current_user, plan_id=plan_id
    )
    try:
        timezone = validate_timezone(request.timezone)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    instruction = request.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="请输入具体的调整要求")

    user_settings = load_user_provider_settings(session, current_user.id)
    provider = get_chat_provider(effective_chat_config(user_settings))
    try:
        with usage_reservation(
            session=session,
            user_id=current_user.id,
            user_settings=user_settings,
            chat_tokens=estimate_chat_reserve(instruction + plan.summary),
        ) as reservation:
            generated = adjust_study_plan(
                session=session,
                plan=plan,
                instruction=instruction,
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

    conversation = session.exec(
        select(Conversation).where(Conversation.id == plan.conversation_id)
    ).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="关联会话不存在")

    try:
        updated_plan = store_generated_plan(
            session=session,
            conversation=conversation,
            generated=generated,
            timezone=timezone,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return plan_public(session=session, plan=updated_plan, user=current_user)


@router.post(
    "/study-plans/{plan_id}/tasks",
    response_model=StudyTaskPublic,
)
def create_study_task(
    plan_id: uuid.UUID,
    request: StudyTaskCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> StudyTaskPublic:
    plan = get_owned_plan_or_404(
        session=session, current_user=current_user, plan_id=plan_id
    )
    if request.start_date > request.end_date:
        raise HTTPException(status_code=422, detail="任务结束日期不能早于开始日期")
    task = StudyTask(
        plan_id=plan.id,
        title=request.title.strip(),
        description=request.description or "",
        start_date=request.start_date,
        end_date=request.end_date,
        estimated_minutes=request.estimated_minutes,
        sort_order=request.sort_order,
        is_completed=False,
    )
    session.add(task)
    if task.start_date < plan.start_date:
        plan.start_date = task.start_date
    if task.end_date > plan.end_date:
        plan.end_date = task.end_date
    plan.updated_at = get_datetime_utc()
    session.add(plan)
    session.commit()
    session.refresh(task)
    return StudyTaskPublic.model_validate(task)


@router.patch("/study-plans/{plan_id}/tasks/{task_id}", response_model=StudyTaskPublic)
def update_study_task(
    plan_id: uuid.UUID,
    task_id: uuid.UUID,
    request: StudyTaskUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> StudyTaskPublic:
    plan = get_owned_plan_or_404(
        session=session, current_user=current_user, plan_id=plan_id
    )
    task = session.exec(
        select(StudyTask)
        .where(StudyTask.id == task_id)
        .where(StudyTask.plan_id == plan_id)
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="学习任务不存在")
    update = request.model_dump(exclude_unset=True)
    if "title" in update and update["title"] is not None:
        title = update["title"].strip()
        if not title:
            raise HTTPException(status_code=422, detail="任务标题不能为空")
        task.title = title
    if "description" in update and update["description"] is not None:
        task.description = update["description"]
    if "start_date" in update and update["start_date"] is not None:
        task.start_date = update["start_date"]
    if "end_date" in update and update["end_date"] is not None:
        task.end_date = update["end_date"]
    if task.start_date > task.end_date:
        raise HTTPException(status_code=422, detail="任务结束日期不能早于开始日期")
    if "estimated_minutes" in update and update["estimated_minutes"] is not None:
        task.estimated_minutes = update["estimated_minutes"]
    if "sort_order" in update and update["sort_order"] is not None:
        task.sort_order = update["sort_order"]
    if "is_completed" in update and update["is_completed"] is not None:
        task.is_completed = update["is_completed"]

    session.add(task)
    # Recalculate plan date bounds
    all_tasks = session.exec(
        select(StudyTask).where(StudyTask.plan_id == plan_id)
    ).all()
    if all_tasks:
        plan.start_date = min(t.start_date for t in all_tasks)
        plan.end_date = max(t.end_date for t in all_tasks)
        plan.updated_at = get_datetime_utc()
        session.add(plan)

    session.commit()
    session.refresh(task)
    return StudyTaskPublic.model_validate(task)


@router.delete("/study-plans/{plan_id}/tasks/{task_id}")
def delete_study_task(
    plan_id: uuid.UUID,
    task_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    plan = get_owned_plan_or_404(
        session=session, current_user=current_user, plan_id=plan_id
    )
    task = session.exec(
        select(StudyTask)
        .where(StudyTask.id == task_id)
        .where(StudyTask.plan_id == plan_id)
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="学习任务不存在")
    session.delete(task)
    session.flush()

    remaining_tasks = session.exec(
        select(StudyTask).where(StudyTask.plan_id == plan_id)
    ).all()
    if remaining_tasks:
        plan.start_date = min(t.start_date for t in remaining_tasks)
        plan.end_date = max(t.end_date for t in remaining_tasks)
        plan.updated_at = get_datetime_utc()
        session.add(plan)
    session.commit()
    return {"message": "学习任务已删除"}


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
