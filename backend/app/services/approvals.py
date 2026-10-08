"""Approval Center: people decide, MATT never approves its own requests."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import ROLE_RANK, ApprovalStatus, RiskLevel, Role, TaskStatus
from app.db.base import utcnow
from app.models import Approval, Experiment, Lead, Task, User
from app.services import audit, events
from app.services.errors import ConflictError, ForbiddenError, NotFoundError


def list_approvals(db: Session, status: str | None = None) -> Sequence[Approval]:
    stmt = select(Approval).order_by(Approval.id.desc()).limit(200)
    if status:
        stmt = stmt.where(Approval.status == status)
    return db.scalars(stmt).all()


def decide(
    db: Session, approval_id: int, user: User, *, approve: bool, note: str | None
) -> Approval:
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise NotFoundError("Approval not found")
    if approval.status != ApprovalStatus.PENDING:
        raise ConflictError(f"Already {approval.status}")
    needed = Role.OWNER if approval.risk_level == RiskLevel.HIGH else Role.ADMIN
    if ROLE_RANK[Role(user.role)] < ROLE_RANK[needed]:
        raise ForbiddenError(f"Only the {needed} can decide {approval.risk_level}-risk approvals")

    approval.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
    approval.decided_by, approval.decided_at, approval.note = str(user.id), utcnow(), note
    _apply(db, approval, approve)
    audit.record(
        db, actor_type="user", actor_id=str(user.id), action=f"approval.{approval.status}",
        target_type="approval", target_id=str(approval.id),
        details={"kind": approval.kind, "action": approval.action},
    )  # fmt: skip
    events.emit(db, "approval.decided", approval_id=approval.id, status=approval.status,
                action=approval.action)  # fmt: skip
    db.commit()
    return approval


def _apply(db: Session, approval: Approval, approve: bool) -> None:
    if approval.kind == "outreach":
        lead = db.get(Lead, int(approval.details.get("lead_id", 0)))
        if lead is not None:
            lead.business.outreach_status = "approved" if approve else "rejected"
            lead.next_action = (
                "Send the approved email yourself; MATT has no email provider connected yet"
                if approve
                else "Outreach rejected; revise or drop this lead"
            )
    elif approval.kind == "code_change":
        from app.services import changes

        changes.decided(db, approval, approve)
    elif approval.kind == "investment":
        exp = db.get(Experiment, int(approval.details.get("experiment_id", 0)))
        if exp is not None and exp.status == "planned":
            exp.status = "running" if approve else "stopped"
            exp.decision = (
                f"Owner approved investing ₹{approval.estimated_cost_inr:,.0f}, paid by the owner "
                "personally; MATT never pays. " + (exp.decision or "")
                if approve
                else "Owner declined the investment. " + (exp.decision or "")
            )[:5000]
    elif approval.kind == "budget" and approval.task_id:
        task = db.get(Task, approval.task_id)
        if task is not None and task.status == TaskStatus.WAITING_APPROVAL:
            if approve:
                task.status, task.next_attempt_at = TaskStatus.QUEUED, None
                task.input = {**task.input, "budget_override": True}
            else:
                task.status, task.finished_at = TaskStatus.CANCELLED, utcnow()
