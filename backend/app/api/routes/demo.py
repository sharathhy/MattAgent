"""Public pages: free demo previews (/p/<token>, unguessable, never indexed) and the
one-click unsubscribe link in offer emails (/u/<lead>/<signature>)."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse

from app.api.deps import AppSettings, DbSession
from app.services import demo_sites, outreach

router = APIRouter(tags=["demo sites"])

#: The strict no-script Content-Security-Policy for these pages is set in app.api.middleware.
HEADERS = {"X-Robots-Tag": "noindex, nofollow"}


@router.get("/p/{token}", response_class=HTMLResponse, include_in_schema=False)
def demo_page(token: str, db: DbSession) -> HTMLResponse:
    row = demo_sites.by_token(db, token)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This preview link does not exist")
    return HTMLResponse(row.content, headers=HEADERS)


_DONE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Unsubscribed</title>
<style>body{font-family:system-ui,sans-serif;max-width:520px;margin:15vh auto;padding:0 20px;
color:#0b1f2a;line-height:1.6}</style></head><body><h1>%s</h1><p>%s</p></body></html>"""


@router.api_route("/u/{lead_id}/{sig}", methods=["GET", "POST"], response_class=HTMLResponse,
                  include_in_schema=False)  # fmt: skip
def unsubscribe(lead_id: int, sig: str, db: DbSession, settings: AppSettings) -> HTMLResponse:
    """One-click unsubscribe (RFC 8058 POST from mail apps, or a plain click)."""
    if not outreach.opt_out(db, settings, lead_id, sig):
        page = _DONE % ("Link not recognised", "This unsubscribe link is not valid.")
        return HTMLResponse(page, status_code=status.HTTP_404_NOT_FOUND, headers=HEADERS)
    page = _DONE % ("You're unsubscribed", "You won't receive any more emails from us. Sorry "
                    "for the interruption.")  # fmt: skip
    return HTMLResponse(page, headers=HEADERS)
