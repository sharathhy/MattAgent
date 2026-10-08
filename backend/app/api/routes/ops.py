"""Command, tasks, workflows, tools, approvals, events, dashboard and settings."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import Admin, AppSettings, CurrentUser, DbSession, Operator, Owner, Router
from app.models import Task, Tool
from app.schemas.ops import (
    ApprovalDecision,
    ApprovalOut,
    AutopilotUpdate,
    CommandRequest,
    CommandResponse,
    EventOut,
    TaskCreate,
    TaskOut,
    ToolOut,
    WorkflowInfo,
    WorkflowRunRequest,
)
from app.services import approvals, autopilot, command, dashboard, events, tasks
from app.workflows import WORKFLOWS

router = APIRouter(tags=["operations"])


def _task_out(task: Task) -> TaskOut:
    out = TaskOut.model_validate(task)
    out.agent_slug = task.agent.slug if task.agent else None
    return out


@router.post("/command", response_model=CommandResponse)
def run_command(
    body: CommandRequest, db: DbSession, user: Operator, model_router: Router
) -> CommandResponse:
    result = command.handle(db, model_router, user, body.text)
    return CommandResponse(
        reply=result.reply, intent=result.intent, task_id=result.task_id, data=result.data
    )


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    db: DbSession,
    _: CurrentUser,
    status: str | None = None,
    agent: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[TaskOut]:
    return [_task_out(t) for t in tasks.list_tasks(db, status, agent, limit)]


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate, db: DbSession, user: Operator) -> TaskOut:
    task = tasks.create(
        db, objective=body.objective, agent_slug=body.agent_slug, created_by=str(user.id),
        priority=body.priority, input={"context": body.context} if body.context else None,
    )  # fmt: skip
    return _task_out(task)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: DbSession, _: CurrentUser) -> TaskOut:
    return _task_out(tasks.get(db, task_id))


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel_task(task_id: int, db: DbSession, user: Operator) -> TaskOut:
    return _task_out(tasks.cancel(db, tasks.get(db, task_id), str(user.id)))


@router.post("/tasks/{task_id}/retry", response_model=TaskOut)
def retry_task(task_id: int, db: DbSession, user: Operator) -> TaskOut:
    return _task_out(tasks.retry(db, tasks.get(db, task_id), str(user.id)))


@router.get("/workflows", response_model=list[WorkflowInfo])
def list_workflows(_: CurrentUser, model_router: Router) -> list[WorkflowInfo]:
    return [
        WorkflowInfo(
            slug=slug,
            description=desc,
            needs_ai_model=needs_ai,
            ready=model_router.available or not needs_ai,
        )
        for slug, (desc, _fn, needs_ai) in WORKFLOWS.items()
    ]


@router.post("/workflows/{slug}/run", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def run_workflow(slug: str, body: WorkflowRunRequest, db: DbSession, user: Operator) -> TaskOut:
    task = tasks.create(
        db, kind="workflow", created_by=str(user.id),
        objective=f"Run {slug.replace('_', ' ')}",
        input={"workflow": slug, "params": body.params},
    )  # fmt: skip
    return _task_out(task)


@router.get("/tools", response_model=list[ToolOut])
def list_tools(db: DbSession, _: CurrentUser) -> list[Tool]:
    return list(db.scalars(select(Tool).order_by(Tool.available.desc(), Tool.name)))


@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(db: DbSession, _: CurrentUser, status: str | None = None) -> list[Any]:
    return list(approvals.list_approvals(db, status))


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalOut)
def decide(approval_id: int, body: ApprovalDecision, db: DbSession, user: Admin) -> Any:
    return approvals.decide(db, approval_id, user, approve=body.approve, note=body.note)


@router.get("/events", response_model=list[EventOut])
def list_events(
    db: DbSession,
    _: CurrentUser,
    after_id: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Any]:
    return list(events.since(db, after_id, limit))


@router.get("/dashboard")
def get_dashboard(
    db: DbSession, _: CurrentUser, model_router: Router, settings: AppSettings
) -> dict[str, Any]:
    return dashboard.overview(db, model_router, settings)


@router.get("/analytics")
def get_analytics(db: DbSession, _: CurrentUser) -> dict[str, Any]:
    return dashboard.analytics(db)


@router.get("/settings")
def get_settings_view(_: Admin, settings: AppSettings, model_router: Router) -> dict[str, Any]:
    """Non-secret configuration. Keys are reported as configured or not, never shown."""
    return {
        "environment": settings.env,
        "owner_email": settings.owner_email,
        "google_sign_in": bool(settings.google_client_id),
        "models": [
            {
                "provider": s.provider,
                "model": s.model,
                "tier": s.tier,
                "quality": s.quality,
                "paid": s.paid,
                "rate_limit": s.rate_limit,
                "enabled": model_router.allowed(s),
            }
            for s in model_router.catalog()
        ],
        "model_keys": {
            "MATT_GEMINI_API_KEY": bool(settings.gemini_api_key),
            "MATT_GROQ_API_KEY": bool(settings.groq_api_key),
            "MATT_OLLAMA_URL": bool(settings.ollama_url),
            "MATT_ANTHROPIC_API_KEY": bool(settings.anthropic_api_key),
        },
        "free_models_only": settings.free_models_only,
        "allow_premium_models": settings.allow_premium_models,
        "daily_ai_budget_inr": settings.daily_ai_budget_inr,
        "monthly_ai_budget_inr": settings.monthly_ai_budget_inr,
        "worker_enabled": settings.worker_enabled,
        "email_sending": False,
    }


@router.get("/autopilot")
def get_autopilot(db: DbSession, _: CurrentUser, model_router: Router) -> dict[str, Any]:
    return autopilot.status(db, model_router)


@router.put("/autopilot")
def update_autopilot(
    body: AutopilotUpdate, db: DbSession, user: Owner, model_router: Router
) -> dict[str, Any]:
    """Only the owner can switch MATT's self-directed work on or off, or retarget it."""
    autopilot.update(db, user, body.model_dump(exclude_none=True))
    return autopilot.status(db, model_router)


@router.post("/autopilot/run", response_model=TaskOut | None)
def run_autopilot_now(db: DbSession, _: Admin, model_router: Router) -> TaskOut | None:
    task = autopilot.tick(db, model_router, force=True)
    return _task_out(task) if task else None
