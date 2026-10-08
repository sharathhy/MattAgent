from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, require_role
from app.core.domain import AgentKind, AgentStatus, Role
from app.models import Agent, User
from app.repositories import agents as agent_repo
from app.schemas.agents import (
    AgentDetail,
    AgentSummary,
    HierarchyNode,
    PermissionChangeRequest,
    RegistrySummary,
    StatusChangeRequest,
)
from app.services import registry

router = APIRouter(prefix="/agents", tags=["agents"])


def _detail(agent: Agent) -> AgentDetail:
    return AgentDetail.model_validate(
        {
            **{k: getattr(agent, k) for k in AgentDetail.model_fields if hasattr(agent, k)},
            "parent_slug": agent.parent.slug if agent.parent else None,
            "report_slugs": [r.slug for r in agent.reports],
        }
    )


@router.get("", response_model=list[AgentSummary])
def list_agents(
    db: DbSession,
    _: CurrentUser,
    kind: AgentKind | None = None,
    department: str | None = None,
    status: AgentStatus | None = None,
    q: str | None = None,
) -> list[Agent]:
    return list(
        agent_repo.list_agents(db, kind=kind, department=department, status=status, search=q)
    )


@router.get("/summary", response_model=RegistrySummary)
def summary(db: DbSession, _: CurrentUser) -> RegistrySummary:
    by_kind = agent_repo.count_by(db, "kind")
    return RegistrySummary(
        total=sum(by_kind.values()),
        by_kind=by_kind,
        by_department=agent_repo.count_by(db, "department"),
        by_status=agent_repo.count_by(db, "status"),
    )


@router.get("/hierarchy", response_model=list[HierarchyNode])
def hierarchy(db: DbSession, _: CurrentUser) -> list[HierarchyNode]:
    agents = agent_repo.list_agents(db)
    nodes = {
        a.id: HierarchyNode(
            slug=a.slug, name=a.name, role=a.role, kind=AgentKind(a.kind),
            department=a.department, status=AgentStatus(a.status),
        )
        for a in agents
    }  # fmt: skip
    roots: list[HierarchyNode] = []
    for a in agents:
        if a.parent_id is None:
            roots.append(nodes[a.id])
        else:
            nodes[a.parent_id].children.append(nodes[a.id])
    return roots


@router.get("/{slug}", response_model=AgentDetail)
def get_agent(slug: str, db: DbSession, _: CurrentUser) -> AgentDetail:
    return _detail(registry.require_agent(db, slug))


@router.patch("/{slug}/status", response_model=AgentDetail)
def change_status(
    slug: str,
    body: StatusChangeRequest,
    db: DbSession,
    actor: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AgentDetail:
    return _detail(registry.transition_status(db, slug, body.status, actor, body.reason))


@router.put("/{slug}/permissions", response_model=AgentDetail)
def change_permissions(
    slug: str,
    body: PermissionChangeRequest,
    db: DbSession,
    actor: Annotated[User, Depends(require_role(Role.OWNER))],
) -> AgentDetail:
    return _detail(registry.set_permissions(db, slug, body.permissions, actor, body.reason))
