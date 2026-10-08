"""Owner change requests for MATT's own code: drafted, approved, then opened as a pull request."""

from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import AppSettings, DbSession, Owner
from app.services import changes

router = APIRouter(prefix="/changes", tags=["changes"])


class ChangeIn(BaseModel):
    request: str = Field(min_length=8, max_length=4000)


@router.get("/config")
def change_config(db: DbSession, _: Owner, settings: AppSettings) -> dict[str, Any]:
    return {
        "github_connected": bool(settings.github_token),
        "repo": settings.github_repo,
        "base_branch": settings.github_base_branch,
        "free_models_only": settings.free_models_only,
        "code_ai": changes.code_ai_status(db, settings),
    }


@router.get("")
def list_changes(db: DbSession, _: Owner) -> list[dict[str, Any]]:
    return [changes.out(c, db) for c in changes.list_changes(db)]


@router.post("", status_code=status.HTTP_201_CREATED)
def request_change(body: ChangeIn, db: DbSession, user: Owner) -> dict[str, Any]:
    """Only the owner can ask MATT to change its own code."""
    return changes.out(changes.create(db, user, body.request), db)
