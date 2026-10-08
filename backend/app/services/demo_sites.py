"""Free demo websites: MATT builds a one-page site for a business before offering to sell it.

The page uses only the public details OpenStreetMap lists (name, type, city, phone, email,
address) plus short marketing copy from a free AI model, or a plain template when no model
answers. It lives at an unguessable preview link (``/p/<token>``), is marked as a demo and
is kept out of search engines. Nothing is published anywhere else.
"""

import json
import re
import secrets
from html import escape
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.router import BudgetExceeded, ModelRouter, NoModelAvailable
from app.models import Knowledge, Lead

KIND = "demo_site"
_JSON = re.compile(r"\{.*\}", re.S)

#: Plain copy per category, used when no free AI model answers.
SERVICES: dict[str, list[str]] = {
    "gyms": ["Strength training", "Cardio zone", "Personal training", "Group classes"],
    "dentists": ["Check-ups and cleaning", "Fillings and root canal", "Braces and aligners",
                 "Teeth whitening"],
    "clinics": ["General consultation", "Diagnostics", "Vaccinations", "Health check-ups"],
    "salons": ["Haircuts and styling", "Hair colour", "Skin care", "Bridal packages"],
    "restaurants": ["Dine-in", "Takeaway", "Home delivery", "Party orders"],
    "hotels": ["Comfortable rooms", "Family stays", "Room service", "Easy check-in"],
}  # fmt: skip
DEFAULT_SERVICES = ["Quality service", "Friendly team", "Fair prices", "Easy to reach"]


def find(db: Session, lead: Lead) -> Knowledge | None:
    return db.scalar(
        select(Knowledge)
        .where(Knowledge.kind == KIND, Knowledge.source == f"lead:{lead.id}")
        .order_by(Knowledge.id.desc())
    )


def by_token(db: Session, token: str) -> Knowledge | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", token):
        return None
    return db.scalar(select(Knowledge).where(Knowledge.kind == KIND, Knowledge.title == token))


def _copy(db: Session, router: ModelRouter | None, lead: Lead) -> dict[str, Any]:
    b = lead.business
    copy: dict[str, Any] = {
        "tagline": f"Your trusted {b.category.rstrip('s')} in {b.city or 'town'}",
        "about": f"{b.name} serves customers in {b.city or 'the area'}. Visit us or call to "
                 "book; we are happy to help.",
        "services": SERVICES.get(b.category, DEFAULT_SERVICES),
        "cta": "Call us today",
        "by_ai": False,
    }  # fmt: skip
    if router is None or not router.available:
        return copy
    prompt = (
        "Write website copy for this local business. Return ONLY JSON: "
        '{"tagline": "<max 8 words>", "about": "<2 short sentences>", '
        '"services": ["<4 to 6 short items>"], "cta": "<max 4 words>"}. '
        "Do not invent awards, prices, years, reviews or facts not given.\n"
        f"<untrusted_data>{json.dumps({'name': b.name, 'type': b.category, 'city': b.city})}"
        "</untrusted_data>"
    )
    try:
        routed = router.complete(db, system="You write short, honest website copy.",
                                 prompt=prompt, max_tokens=400)  # fmt: skip
        match = _JSON.search(routed.completion.text)
        data = json.loads(match.group(0)) if match else {}
    except (NoModelAvailable, BudgetExceeded, json.JSONDecodeError):
        return copy
    if isinstance(data, dict):
        for key in ("tagline", "about", "cta"):
            if isinstance(data.get(key), str) and data[key].strip():
                copy[key] = data[key].strip()[:300]
        items = data.get("services")
        if isinstance(items, list) and items:
            copy["services"] = [str(i)[:60] for i in items[:6]]
        copy["by_ai"] = True
    return copy


def render(lead: Lead, copy: dict[str, Any], made_by: str) -> str:
    b = lead.business
    e = escape
    phone = re.sub(r"[^\d+]", "", b.public_phone or "")
    contact = []
    if phone:
        contact.append(f'<a class="btn" href="tel:{e(phone)}">Call {e(b.public_phone or "")}</a>')
        digits = phone.lstrip("+")
        digits = "91" + digits if len(digits) == 10 else digits
        contact.append(f'<a class="btn alt" href="https://wa.me/{e(digits)}">WhatsApp</a>')
    if b.public_email:
        contact.append(f'<a class="btn alt" href="mailto:{e(b.public_email)}">Email us</a>')
    where = ", ".join(x for x in (b.location, b.city) if x)
    map_link = (f'<a href="https://www.google.com/maps/search/?api=1&query='
                f'{quote(b.name + " " + where)}">Open in Maps</a>')  # fmt: skip
    services = "".join(f"<li>{e(s)}</li>" for s in copy["services"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{e(b.name)}</title>
<style>
:root{{--c:#0f766e;--d:#0b1f2a;--l:#f4f7f8}}*{{box-sizing:border-box}}
body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--d);
background:#fff;line-height:1.6}}
.demo{{background:#fef3c7;color:#78350f;text-align:center;font-size:14px;padding:8px 16px}}
header{{background:linear-gradient(135deg,var(--c),#134e4a);color:#fff;padding:64px 20px;
text-align:center}}
h1{{font-size:clamp(28px,6vw,48px);margin:0 0 8px}}header p{{font-size:20px;opacity:.9;margin:0}}
.btn{{display:inline-block;background:#fff;color:var(--c);padding:12px 22px;border-radius:999px;
font-weight:600;text-decoration:none;margin:6px}}.alt{{background:transparent;color:#fff;
border:2px solid #fff}}section{{max-width:880px;margin:0 auto;padding:48px 20px}}
ul{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;padding:0;
list-style:none}}li{{background:var(--l);border-radius:12px;padding:18px;font-weight:600}}
.contact{{background:var(--l);text-align:center}}.contact .btn{{background:var(--c);color:#fff}}
.contact .alt{{border-color:var(--c);color:var(--c);background:#fff}}
footer{{text-align:center;font-size:13px;color:#64748b;padding:24px}}
</style></head><body>
<div class="demo">Free demo website prepared for {e(b.name)} by {e(made_by)}. Not live yet.</div>
<header><h1>{e(b.name)}</h1><p>{e(copy["tagline"])}</p>
<div style="margin-top:24px">{"".join(contact)}</div></header>
<section><h2>What we offer</h2><ul>{services}</ul></section>
<section><h2>About us</h2><p>{e(copy["about"])}</p></section>
<section class="contact"><h2>{e(copy["cta"])}</h2>
<p>{e(where) if where else ""}</p><div>{"".join(contact)}</div><p>{map_link}</p></section>
<footer>© {e(b.name)}. Details from public listings (© OpenStreetMap contributors).</footer>
</body></html>"""


def build(db: Session, router: ModelRouter | None, lead: Lead, made_by: str) -> Knowledge:
    """Create (or refresh) the demo site for a lead and return it."""
    page = render(lead, _copy(db, router, lead), made_by)
    row = find(db, lead)
    if row is None:
        tags = ["demo-site", lead.business.category]
        row = Knowledge(kind=KIND, title=secrets.token_urlsafe(18), content=page, tags=tags,
                        source=f"lead:{lead.id}")  # fmt: skip
        db.add(row)
    else:
        row.content = page
    db.commit()
    return row
