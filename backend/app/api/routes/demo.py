"""Public preview links for free demo websites: /p/<token>, unguessable, never indexed."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse

from app.api.deps import DbSession
from app.services import demo_sites

router = APIRouter(tags=["demo sites"])

#: The strict no-script Content-Security-Policy for these pages is set in app.api.middleware.
HEADERS = {"X-Robots-Tag": "noindex, nofollow"}


@router.get("/p/{token}", response_class=HTMLResponse, include_in_schema=False)
def demo_page(token: str, db: DbSession) -> HTMLResponse:
    row = demo_sites.by_token(db, token)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This preview link does not exist")
    return HTMLResponse(row.content, headers=HEADERS)
