"""Tool registry: keeps the ``tools`` table in sync with the plugin definitions."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tool
from app.plugins.registry import BY_SLUG, IMPLEMENTED, TOOLS
from app.services.errors import NotFoundError, ServiceError


def seed_tools(db: Session) -> int:
    existing = {t.slug: t for t in db.scalars(select(Tool))}
    for d in TOOLS:
        row = existing.get(d.slug) or Tool(slug=d.slug)
        row.name, row.description, row.provider = d.name, d.description, d.provider
        row.cost_tier, row.permission, row.risk_level = d.cost_tier, d.permission, d.risk_level
        row.input_schema, row.output_schema, row.version = (
            d.input_schema,
            d.output_schema,
            d.version,
        )
        row.available = d.slug in IMPLEMENTED
        db.add(row)
    db.commit()
    return len(TOOLS)


def invoke(slug: str, **kwargs: Any) -> dict[str, Any]:
    definition = BY_SLUG.get(slug)
    if definition is None:
        raise NotFoundError(f"Unknown tool {slug!r}")
    if slug not in IMPLEMENTED or definition.run is None:
        raise ServiceError(f"Tool {slug!r} is not connected yet")
    return definition.run(**kwargs)
