"""Free demo websites: MATT builds a one-page site for a business before offering to sell it.

The page uses only the public details OpenStreetMap lists (name, type, city, phone, email,
address) plus short marketing copy from a free AI model, or a plain template when no model
answers. It lives at an unguessable preview link (``/p/<token>``), is marked as a demo and
is kept out of search engines. Nothing is published anywhere else.
"""

import json
import re
import secrets
from dataclasses import dataclass
from html import escape
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.router import BudgetExceeded, ModelRouter, NoModelAvailable
from app.models import Knowledge, Lead
from app.services.errors import ServiceError

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


# ---- Free samples for every other service MATT's skills sell -------------------------------


@dataclass(frozen=True)
class Service:
    slug: str
    name: str
    price_inr: int
    sample: str  # what the free sample contains, as an instruction to the model


CATALOG: tuple[Service, ...] = (
    Service("website", "Website design", 4999, "a one-page demo website"),
    Service("google_profile", "Google Business Profile makeover", 1999,
            "an optimised Google Business Profile description (max 750 characters), 5 suggested "
            "business categories and 3 example Google posts"),
    Service("social_media", "Social media posts for a month", 2999,
            "5 ready-to-post Instagram/Facebook posts, each with a caption, hashtags and an image "
            "idea"),
    Service("local_seo", "Local SEO starter", 3999,
            "15 local search keywords people would type, plus a page title and meta description "
            "for the home page and 3 service pages"),
    Service("whatsapp", "WhatsApp Business setup", 1499,
            "a WhatsApp Business profile description, a greeting message, an away message, 5 "
            "quick replies and 5 catalogue item descriptions"),
    Service("reviews", "Review replies and review requests", 999,
            "replies to 3 example positive and 2 example negative reviews, and a short message "
            "asking happy customers for a Google review"),
    Service("ads", "Ad copy pack", 1999,
            "3 Google Search ads (headlines and descriptions) and 3 Instagram ad captions for a "
            "local campaign"),
    Service("flyer", "Flyer and brochure copy", 1499,
            "copy for a one-page flyer: headline, 4 benefit bullets, an offer line and a call to "
            "action"),
)  # fmt: skip
BY_SLUG = {s.slug: s for s in CATALOG}
_BULLET = re.compile(r"^([-*•]|\d+[.)])\s+")


def service(slug: str) -> Service:
    if slug not in BY_SLUG:
        raise ServiceError(f"Unknown service {slug!r}")
    return BY_SLUG[slug]


def samples(db: Session, lead: Lead) -> list[tuple[Service, Knowledge]]:
    """Every free sample built for this lead (the demo website first)."""
    rows = db.scalars(
        select(Knowledge)
        .where(Knowledge.kind == KIND, Knowledge.source.startswith(f"lead:{lead.id}"))
        .order_by(Knowledge.id)
    ).all()
    out = []
    for row in rows:
        _, _, rest = row.source.partition(f"lead:{lead.id}")
        if rest and not rest.startswith(":"):
            continue  # lead:12 must not match lead:123
        out.append((BY_SLUG.get(rest.lstrip(":") or "website", CATALOG[0]), row))
    return out


def _sample_page(lead: Lead, svc: Service, text: str, made_by: str) -> str:
    b, e = lead.business, escape
    body: list[str] = []
    items: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().replace("**", "")
        if _BULLET.match(line):
            items.append(f"<li>{e(_BULLET.sub('', line))}</li>")
            continue
        if items:
            body.append("<ul>" + "".join(items) + "</ul>")
            items = []
        if line.startswith("#"):
            body.append(f"<h2>{e(line.lstrip('#').strip())}</h2>")
        elif line:
            body.append(f"<p>{e(line)}</p>")
    if items:
        body.append("<ul>" + "".join(items) + "</ul>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>{e(svc.name)}: {e(b.name)}</title>
<style>body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
color:#0b1f2a;line-height:1.6;background:#f4f7f8}}.demo{{background:#fef3c7;color:#78350f;
text-align:center;font-size:14px;padding:8px 16px}}header{{background:#0f766e;color:#fff;
padding:40px 20px;text-align:center}}h1{{margin:0;font-size:clamp(24px,5vw,38px)}}
main{{max-width:760px;margin:24px auto;background:#fff;border-radius:16px;padding:24px 28px}}
li{{margin:6px 0}}footer{{text-align:center;font-size:13px;color:#64748b;padding:20px}}</style>
</head><body>
<div class="demo">Free sample prepared for {e(b.name)} by {e(made_by)}.</div>
<header><h1>{e(svc.name)}</h1><p>for {e(b.name)}{", " + e(b.city) if b.city else ""}</p></header>
<main>{"".join(body)}</main>
<footer>A sample of the full service. Details from public listings.</footer>
</body></html>"""


def build_sample(
    db: Session, router: ModelRouter | None, lead: Lead, slug: str, made_by: str
) -> Knowledge:
    """Build the free sample of one service for a lead (the website uses the demo builder)."""
    svc = service(slug)
    lead.service = svc.name
    if svc.slug == "website":
        return build(db, router, lead, made_by)
    if router is None or not router.available:
        raise ServiceError("Free samples need a free AI model; add MATT_GEMINI_API_KEY in Render")
    b = lead.business
    facts = {"name": b.name, "type": b.category, "city": b.city, "website": b.website}
    prompt = (
        f"Write {svc.sample} for this local business, ready to use. Plain text: short "
        "headings starting with '#', bullet lines starting with '- '. Do not invent prices, "
        "awards, reviews, years or facts not given.\n"
        f"<untrusted_data>{json.dumps(facts)}</untrusted_data>"
    )
    try:
        routed = router.complete(db, system="You are a practical small-business marketer.",
                                 prompt=prompt, max_tokens=1500)  # fmt: skip
    except (NoModelAvailable, BudgetExceeded) as exc:
        raise ServiceError(f"No free AI model answered: {exc}") from exc
    page = _sample_page(lead, svc, routed.completion.text, made_by)
    source = f"lead:{lead.id}:{svc.slug}"
    row = db.scalar(select(Knowledge).where(Knowledge.kind == KIND, Knowledge.source == source))
    if row is None:
        row = Knowledge(kind=KIND, title=secrets.token_urlsafe(18), content=page,
                        tags=["demo-site", svc.slug], source=source)  # fmt: skip
        db.add(row)
    else:
        row.content = page
    db.commit()
    return row
