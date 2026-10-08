"""Task queue: create, claim, execute with retries, and record results.

Tasks live in the database and a worker thread polls for them, so the queue survives restarts
and needs no extra infrastructure. Failures retry with exponential backoff; an exhausted budget
parks the task behind an owner approval instead of failing it.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents import runtime
from app.core import money
from app.core.domain import (
    ACTIVE_TASK_STATUSES,
    AgentStatus,
    ApprovalStatus,
    RiskLevel,
    TaskStatus,
)
from app.db.base import utcnow
from app.llm.router import BudgetExceeded, ModelRouter, NoModelAvailable
from app.models import Agent, Approval, Task
from app.services import events
from app.services.errors import ConflictError, NotFoundError, ServiceError
from app.workflows import WORKFLOWS, Context, run_workflow

log = logging.getLogger(__name__)

BACKOFF_SECONDS = 5
MAX_DELEGATION_DEPTH = 3


def create(
    db: Session,
    *,
    objective: str,
    created_by: str,
    kind: str = "agent",
    agent_slug: str | None = None,
    input: dict[str, Any] | None = None,
    priority: int = 5,
    parent: Task | None = None,
    commit: bool = True,
) -> Task:
    money.refuse_outbound(objective)  # main rule: receive-only, above any approval
    agent = None
    if kind == "agent":
        agent = db.scalar(select(Agent).where(Agent.slug == (agent_slug or "ceo")))
        if agent is None:
            raise NotFoundError(f"Agent {agent_slug!r} not found")
        if agent.status == AgentStatus.RETIRED:
            raise ConflictError(f"{agent.name} is retired")
    elif kind == "workflow":
        if (input or {}).get("workflow") not in WORKFLOWS:
            raise NotFoundError("Unknown workflow")
    else:
        raise ServiceError(f"Unknown task kind {kind!r}")
    task = Task(
        kind=kind, objective=objective.strip()[:4000], agent_id=agent.id if agent else None,
        parent_id=parent.id if parent else None, status=TaskStatus.QUEUED,
        priority=max(1, min(priority, 10)), input=input or {}, created_by=created_by,
    )  # fmt: skip
    db.add(task)
    db.flush()
    events.emit(db, "task.created", task_id=task.id, objective=task.objective[:200],
                agent=agent.slug if agent else None, kind=kind)  # fmt: skip
    if commit:
        db.commit()
    return task


def list_tasks(
    db: Session, status: str | None = None, agent_slug: str | None = None, limit: int = 100
) -> Sequence[Task]:
    stmt = select(Task).order_by(Task.id.desc()).limit(min(limit, 500))
    if status:
        stmt = stmt.where(Task.status == status)
    if agent_slug:
        stmt = stmt.join(Agent, Task.agent_id == Agent.id).where(Agent.slug == agent_slug)
    return db.scalars(stmt).all()


def get(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError("Task not found")
    return task


def cancel(db: Session, task: Task, actor: str) -> Task:
    if task.status not in ACTIVE_TASK_STATUSES or task.status == TaskStatus.RUNNING:
        raise ConflictError(f"A {task.status} task cannot be cancelled")
    task.status = TaskStatus.CANCELLED
    task.finished_at = utcnow()
    events.emit(db, "task.cancelled", task_id=task.id, by=actor)
    db.commit()
    return task


def retry(db: Session, task: Task, actor: str) -> Task:
    if task.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
        raise ConflictError("Only failed or cancelled tasks can be retried")
    task.status, task.error, task.attempts = TaskStatus.QUEUED, None, 0
    task.next_attempt_at = None
    events.emit(db, "task.retried", task_id=task.id, by=actor)
    db.commit()
    return task


def claim_next(db: Session) -> Task | None:
    now = utcnow()
    stmt = (
        select(Task)
        .where(Task.status == TaskStatus.QUEUED)
        .where(or_(Task.next_attempt_at.is_(None), Task.next_attempt_at <= now))
        .order_by(Task.priority, Task.id)
        .limit(1)
    )
    if db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    task = db.scalar(stmt)
    if task is None:
        db.rollback()
        return None
    task.status = TaskStatus.RUNNING
    task.attempts += 1
    task.started_at = task.started_at or now
    events.emit(db, "task.started", task_id=task.id, objective=task.objective[:200])
    db.commit()
    return task


def _depth(db: Session, task: Task) -> int:
    depth, current = 0, task
    while current.parent_id is not None and depth < 10:
        parent = db.get(Task, current.parent_id)
        if parent is None:
            break
        depth, current = depth + 1, parent
    return depth


def _update_agent_metrics(agent: Agent | None, success: bool) -> None:
    if agent is None:
        return
    if success:
        agent.tasks_completed += 1
    else:
        agent.tasks_failed += 1
    total = agent.tasks_completed + agent.tasks_failed
    agent.success_rate = round(agent.tasks_completed / total, 3) if total else None


def execute(db: Session, task: Task, router: ModelRouter) -> Task:
    """Run a claimed task to an end state (or back to queued for a retry)."""
    override = bool(task.input.get("budget_override"))
    try:
        if task.kind == "workflow":
            ctx = Context(db=db, router=router, task_id=task.id, override_budget=override)
            data = run_workflow(ctx, task.input["workflow"], task.input.get("params", {}))
            task.output = str(data.get("summary", "Done"))
            task.output_data = data
        else:
            if task.agent is None:
                raise ServiceError("Agent task has no agent")
            result = runtime.run(
                db, router, task.agent, task.objective, context=task.input.get("context"),
                task_id=task.id, override_budget=override,
            )  # fmt: skip
            task.output = result.text
            if result.routed:
                task.model = result.routed.spec.model
                task.cost_inr = (task.cost_inr or Decimal("0")) + result.routed.cost_inr
                c = result.routed.completion
                task.tokens += c.prompt_tokens + c.completion_tokens
            if result.delegations and _depth(db, task) < MAX_DELEGATION_DEPTH:
                subs = [
                    create(
                        db,
                        objective=o,
                        created_by=f"agent:{task.agent.slug}",
                        agent_slug=s,
                        parent=task,
                        commit=False,
                    )
                    for s, o in result.delegations
                    if not money.is_outbound(o)
                ]
                task.output_data = {"delegated_task_ids": [t.id for t in subs]}
        task.status = TaskStatus.SUCCEEDED
        task.finished_at = utcnow()
        _update_agent_metrics(task.agent, True)
        events.emit(db, "task.succeeded", task_id=task.id, summary=(task.output or "")[:300])
    except BudgetExceeded as exc:
        db.rollback()
        task.status = TaskStatus.WAITING_APPROVAL
        task.error = str(exc)
        approval = Approval(
            task_id=task.id, agent_slug=task.agent.slug if task.agent else "matt",
            action=f"Exceed the AI budget to finish: {task.objective[:200]}", kind="budget",
            details={"reason": str(exc)}, risk_level=RiskLevel.MEDIUM,
            status=ApprovalStatus.PENDING,
        )  # fmt: skip
        db.add(approval)
        db.flush()
        events.emit(db, "approval.requested", approval_id=approval.id, action=approval.action)
    except (NoModelAvailable, ServiceError) as exc:
        db.rollback()
        _fail(
            db, task, str(exc), retryable=isinstance(exc, NoModelAvailable) and "failed" in str(exc)
        )
    except Exception as exc:
        db.rollback()
        log.exception("task crashed", extra={"task_id": task.id})
        _fail(db, task, f"{type(exc).__name__}: {exc}", retryable=True)
    db.commit()
    return task


def _fail(db: Session, task: Task, error: str, *, retryable: bool) -> None:
    task.error = error[:2000]
    if retryable and task.attempts < task.max_attempts:
        task.status = TaskStatus.QUEUED
        task.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=BACKOFF_SECONDS * 2 ** (task.attempts - 1)
        )
        events.emit(db, "task.retrying", task_id=task.id, attempt=task.attempts, error=error[:300])
        return
    task.status = TaskStatus.FAILED
    task.finished_at = utcnow()
    _update_agent_metrics(task.agent, False)
    events.emit(db, "task.failed", task_id=task.id, error=error[:300])


def process_next(db: Session, router: ModelRouter) -> Task | None:
    task = claim_next(db)
    return execute(db, task, router) if task else None
