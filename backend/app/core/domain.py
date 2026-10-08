"""Core domain vocabulary shared by models, schemas and services."""

from enum import StrEnum


class Role(StrEnum):
    """Human user roles (RBAC). Ordered from most to least privileged."""

    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


ROLE_RANK = {Role.OWNER: 3, Role.ADMIN: 2, Role.OPERATOR: 1, Role.VIEWER: 0}


class Permission(StrEnum):
    """Agent permission levels (spec section 21)."""

    READ = "read"
    WRITE = "write"
    EXTERNAL_ACTION = "external_action"
    FINANCIAL = "financial"
    ADMIN = "admin"


#: Permissions whose use always requires explicit owner approval.
HIGH_RISK_PERMISSIONS = frozenset(
    {Permission.EXTERNAL_ACTION, Permission.FINANCIAL, Permission.ADMIN}
)


class AgentKind(StrEnum):
    CEO = "ceo"
    EXECUTIVE = "executive"
    SKILL = "skill"
    META = "meta"  # permanent self-upgrade skills


class AgentStatus(StrEnum):
    """Worker lifecycle (spec section 6)."""

    DISCOVERED = "discovered"
    DESIGNED = "designed"
    BUILT = "built"
    TESTING = "testing"
    EVALUATED = "evaluated"
    DEPLOYED = "deployed"
    UPGRADING = "upgrading"
    RETIRED = "retired"


# DISCOVER -> DESIGN -> BUILD -> TEST -> EVALUATE -> DEPLOY -> (MONITOR) -> UPGRADE
# -> RE-EVALUATE (back through testing) -> RETIRE.
# A failed test or evaluation goes back to building. Any non-retired worker can be retired.
AGENT_TRANSITIONS: dict[AgentStatus, frozenset[AgentStatus]] = {
    AgentStatus.DISCOVERED: frozenset({AgentStatus.DESIGNED}),
    AgentStatus.DESIGNED: frozenset({AgentStatus.BUILT}),
    AgentStatus.BUILT: frozenset({AgentStatus.TESTING}),
    AgentStatus.TESTING: frozenset({AgentStatus.EVALUATED, AgentStatus.BUILT}),
    AgentStatus.EVALUATED: frozenset({AgentStatus.DEPLOYED, AgentStatus.BUILT}),
    AgentStatus.DEPLOYED: frozenset({AgentStatus.UPGRADING}),
    AgentStatus.UPGRADING: frozenset({AgentStatus.TESTING}),
    AgentStatus.RETIRED: frozenset(),
}


def can_transition(current: AgentStatus, target: AgentStatus) -> bool:
    if target is AgentStatus.RETIRED:
        return current is not AgentStatus.RETIRED
    return target in AGENT_TRANSITIONS[current]


class CostTier(StrEnum):
    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
