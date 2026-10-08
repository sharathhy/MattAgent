from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import AppSettings, DbSession

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: DbSession, settings: AppSettings, response: Response) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "env": settings.env,
    }
