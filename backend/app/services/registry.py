"""Agent registry: catalog seeding, lifecycle transitions and permission changes."""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.domain import (
    HIGH_RISK_PERMISSIONS,
    AgentStatus,
    Permission,
    Role,
    can_transition,
)
from app.db.base import utcnow
from app.models import Agent, AgentVersion, User
from app.registry.catalog import AgentDefinition, load_catalog
from app.repositories import agents as agent_repo
from app.services import audit
from app.services.errors import ConflictError, ForbiddenError, NotFoundError

log = logging.getLogger(__name__)

#: Catalog fields copied onto the Agent row.
_DEFINITION_FIELDS = (
    "slug", "name", "role", "kind", "department", "description", "capabilities",
    "inputs", "outputs", "tools", "permissions", "dependencies", "cost_tier", "level",
)  # fmt: skip


@dataclass(frozen=True)
class SeedResult:
    created: int
    existing: int


def snapshot(agent: Agent) -> dict[str, Any]:
    data = {f: getattr(agent, f) for f in _DEFINITION_FIELDS}
    data["status"] = agent.status
    data["version"] = agent.version
    return data


def seed_registry(
    db: Session, definitions: tuple[AgentDefinition, ...] | None = None
) -> SeedResult:
    """Insert catalog agents that are not yet registered. Existing agents are never overwritten,
    so owner-made changes (status, permissions) survive re-seeding."""
    definitions = definitions or load_catalog()
    by_slug: dict[str, Agent] = {}
    created = existing = 0
    for d in definitions:
        agent = agent_repo.get_by_slug(db, d.slug)
        if agent is not None:
            existing += 1
        else:
            parent = by_slug.get(d.parent_slug) if d.parent_slug else None
            agent = Agent(
                **d.model_dump(include=set(_DEFINITION_FIELDS)),
                parent=parent,
                status=AgentStatus.DESIGNED,
                version="1.0.0",
            )
            agent.versions.append(
                AgentVersion(
                    version="1.0.0",
                    change_summary="Registered from workforce catalog",
                    snapshot=snapshot(agent),
                    created_by="system:catalog",
                )
            )
            db.add(agent)
            created += 1
        by_slug[d.slug] = agent
    if created:
        db.flush()
        audit.record(
            db, actor_type="system", actor_id="catalog", action="registry.seeded",
            details={"created": created, "existing": existing},
        )  # fmt: skip
    db.commit()
    log.info("registry seeded", extra={"agents_created": created, "agents_existing": existing})
    return SeedResult(created=created, existing=existing)


def require_agent(db: Session, slug: str) -> Agent:
    agent = agent_repo.get_by_slug(db, slug)
    if agent is None:
        raise NotFoundError(f"Agent '{slug}' not found")
    return agent


def transition_status(
    db: Session, slug: str, target: AgentStatus, actor: User, reason: str
) -> Agent:
    agent = require_agent(db, slug)
    current = AgentStatus(agent.status)
    if not can_transition(current, target):
        raise ConflictError(f"Cannot move agent from '{current}' to '{target}'")
    agent.status = target
    audit.record(
        db, actor_type="user", actor_id=str(actor.id), action="agent.status_changed",
        target_type="agent", target_id=slug,
        details={"from": current, "to": target, "reason": reason},
    )  # fmt: skip
    db.commit()
    return agent


def _bump_patch(version: str) -> str:
    major, minor, patch = (int(p) for p in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def set_permissions(
    db: Session, slug: str, permissions: list[Permission], actor: User, reason: str
) -> Agent:
    """Replace an agent's permissions. Only the owner may change permissions, and every change is
    versioned and audited. There is deliberately no code path for an agent to change its own."""
    if actor.role != Role.OWNER:
        raise ForbiddenError("Only the owner can change agent permissions")
    agent = require_agent(db, slug)
    before = set(agent.permissions)
    after = {Permission(p) for p in permissions}
    if before == after:
        return agent
    agent.permissions = sorted(after)
    agent.version = _bump_patch(agent.version)
    agent.last_upgraded_at = utcnow()
    granted = sorted(after - before)
    revoked = sorted(before - after)
    agent.versions.append(
        AgentVersion(
            version=agent.version,
            change_summary=f"Permissions changed: +{granted} -{revoked}. {reason}".strip(),
            snapshot=snapshot(agent),
            created_by=f"user:{actor.id}",
        )
    )
    audit.record(
        db, actor_type="user", actor_id=str(actor.id), action="agent.permissions_changed",
        target_type="agent", target_id=slug,
        details={
            "granted": granted, "revoked": revoked, "reason": reason,
            "high_risk_granted": sorted(set(granted) & HIGH_RISK_PERMISSIONS),
        },
    )  # fmt: skip
    db.commit()
    return agent
