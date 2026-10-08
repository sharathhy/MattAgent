"""Load and validate the workforce catalog (``data/workforce.yaml``)."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.core.domain import AgentKind, CostTier, Permission

CATALOG_PATH = Path(__file__).parent / "data" / "workforce.yaml"


class AgentDefinition(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str
    role: str
    kind: AgentKind
    department: str
    parent_slug: str | None
    description: str
    capabilities: list[str]
    inputs: list[str] = []
    outputs: list[str] = []
    tools: list[str] = []
    permissions: list[Permission]
    dependencies: list[str] = []
    cost_tier: CostTier
    level: str = "standard"


class CatalogError(ValueError):
    pass


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_catalog(raw: dict[str, Any]) -> list[AgentDefinition]:
    """Expand the compact catalog format into full definitions, parents before children."""
    defs: list[AgentDefinition] = []

    ceo = raw["ceo"]
    defs.append(AgentDefinition(kind=AgentKind.CEO, parent_slug=None, **ceo))

    exec_defaults = raw.get("executive_defaults", {})
    for entry in raw["executives"]:
        defs.append(
            AgentDefinition(
                kind=AgentKind.EXECUTIVE, parent_slug=ceo["slug"], **{**exec_defaults, **entry}
            )
        )

    categories: dict[str, Any] = raw["categories"]
    for category, entries in raw["skills"].items():
        if category not in categories:
            raise CatalogError(f"Skill category '{category}' has no definition under 'categories'")
        cat = categories[category]
        kind = AgentKind(cat.get("kind", AgentKind.SKILL))
        for entry in entries:
            merged = {**cat["defaults"], **entry}
            merged.setdefault("slug", slugify(entry["name"]))
            merged.setdefault("role", entry["name"])
            defs.append(
                AgentDefinition(
                    kind=kind,
                    department=cat["department"],
                    parent_slug=cat["reports_to"],
                    **merged,
                )
            )

    _validate_references(defs)
    return defs


def _validate_references(defs: list[AgentDefinition]) -> None:
    seen: set[str] = set()
    for d in defs:
        if d.slug in seen:
            raise CatalogError(f"Duplicate agent slug '{d.slug}'")
        seen.add(d.slug)
    for d in defs:
        if d.parent_slug is not None and d.parent_slug not in seen:
            raise CatalogError(f"'{d.slug}' reports to unknown agent '{d.parent_slug}'")
        missing = [dep for dep in d.dependencies if dep not in seen]
        if missing:
            raise CatalogError(f"'{d.slug}' depends on unknown agents {missing}")


@lru_cache
def load_catalog(path: Path = CATALOG_PATH) -> tuple[AgentDefinition, ...]:
    with path.open(encoding="utf-8") as fh:
        return tuple(parse_catalog(yaml.safe_load(fh)))
