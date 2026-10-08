import pytest

from app.core.domain import HIGH_RISK_PERMISSIONS, AgentKind
from app.registry.catalog import CatalogError, load_catalog, parse_catalog


def test_catalog_has_full_initial_workforce() -> None:
    defs = load_catalog()
    kinds = [d.kind for d in defs]
    assert kinds.count(AgentKind.CEO) == 1
    assert kinds.count(AgentKind.EXECUTIVE) == 9
    assert kinds.count(AgentKind.SKILL) == 100
    assert kinds.count(AgentKind.META) == 10


def test_parents_precede_children() -> None:
    seen: set[str] = set()
    for d in load_catalog():
        assert d.parent_slug is None or d.parent_slug in seen
        seen.add(d.slug)


def test_external_actions_are_limited_to_outbound_roles() -> None:
    risky = {d.slug for d in load_catalog() if set(d.permissions) & HIGH_RISK_PERMISSIONS}
    # Research and analysis roles must never be able to act externally or move money.
    assert "web-researcher" not in risky
    assert "sales-copywriter" not in risky
    assert {"follow-up-agent", "email-marketing-agent", "cfo"} <= risky


def _minimal(**skills: list[dict[str, object]]) -> dict[str, object]:
    return {
        "ceo": {"slug": "ceo", "name": "CEO", "role": "CEO", "department": "exec",
                "description": "d", "capabilities": [], "permissions": ["read"],
                "cost_tier": "low"},
        "executives": [],
        "categories": {"ops": {"department": "ops", "reports_to": "ceo",
                               "defaults": {"permissions": ["read"], "cost_tier": "free"}}},
        "skills": skills,
    }  # fmt: skip


def test_duplicate_slugs_rejected() -> None:
    entry = {"name": "Dup", "description": "d", "capabilities": []}
    with pytest.raises(CatalogError, match="Duplicate"):
        parse_catalog(_minimal(ops=[entry, entry]))


def test_unknown_dependency_rejected() -> None:
    entry = {"name": "A", "description": "d", "capabilities": [], "dependencies": ["missing"]}
    with pytest.raises(CatalogError, match="unknown agents"):
        parse_catalog(_minimal(ops=[entry]))


def test_invalid_permission_rejected() -> None:
    entry = {"name": "A", "description": "d", "capabilities": [], "permissions": ["root"]}
    with pytest.raises(ValueError):
        parse_catalog(_minimal(ops=[entry]))
