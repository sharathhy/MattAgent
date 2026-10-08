"""Code-defined workflows. Each one does real work with real data, or fails honestly."""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import runtime
from app.core.domain import ApprovalStatus, LeadStatus, RiskLevel, Truth
from app.llm.router import ModelRouter, NoModelAvailable
from app.models import Agent, Approval, Business, Lead, Opportunity
from app.plugins import business_discovery, website_auditor
from app.services import events
from app.services.errors import NotFoundError, ServiceError
from app.services.scoring import FACTORS, SERVICE_VALUE_INR, opportunity_score, website_lead

log = logging.getLogger(__name__)


@dataclass
class Context:
    db: Session
    router: ModelRouter
    task_id: int | None = None
    override_budget: bool = False

    def emit(self, type: str, **payload: Any) -> None:
        events.emit(self.db, type, task_id=self.task_id, **payload)
        self.db.commit()


Workflow = Callable[[Context, dict[str, Any]], dict[str, Any]]


def _agent(db: Session, slug: str) -> Agent:
    agent = db.scalar(select(Agent).where(Agent.slug == slug))
    if agent is None:
        raise NotFoundError(f"Agent {slug!r} is not in the registry")
    return agent


def _upsert_business(db: Session, data: dict[str, Any]) -> tuple[Business, bool]:
    row = db.scalar(
        select(Business).where(
            Business.source == data["source"], Business.source_ref == data["source_ref"]
        )
    )
    created = row is None
    row = row or Business(source=data["source"], source_ref=data["source_ref"])
    for key in ("name", "category", "city", "country", "location", "website", "public_phone",
                "public_email", "source_url"):  # fmt: skip
        if data.get(key) is not None:
            setattr(row, key, data[key])
    db.add(row)
    db.flush()
    return row, created


def _apply_audit(business: Business, audit: dict[str, Any]) -> None:
    business.audit = audit
    business.audited_at = datetime.now(UTC)
    business.website_score = audit["website_score"]
    business.technology_stack = audit["technology_stack"]
    business.social_links = audit["social_links"]
    if not business.public_email and audit["public_emails"]:
        business.public_email = audit["public_emails"][0]


def _ensure_lead(db: Session, business: Business) -> Lead | None:
    decision = website_lead(business.website, business.website_score)
    if decision is None:
        return None
    service, score = decision
    business.opportunity_score = score
    lead = db.scalar(select(Lead).where(Lead.business_id == business.id))
    if lead is not None:
        return lead
    low, high = SERVICE_VALUE_INR[service]
    next_action = (
        "Verify the business really has no website (OpenStreetMap may just not list it)"
        if not business.website
        else "Review the audit, then draft outreach"
    )
    lead = Lead(
        business_id=business.id, status=LeadStatus.NEW, service=service,
        estimated_value_min_inr=low, estimated_value_max_inr=high, next_action=next_action,
        notes="Value range is an ASSUMPTION based on typical small-business website pricing "
        "in India, not a quote.",
    )  # fmt: skip
    business.lead_status = LeadStatus.NEW
    db.add(lead)
    return lead


def website_opportunities(ctx: Context, params: dict[str, Any]) -> dict[str, Any]:
    """Discover businesses, audit their websites, score them and create leads."""
    city = str(params.get("city", "")).strip()
    category = str(params.get("category", "")).strip()
    if not city or not category:
        raise ServiceError("Both a city and a category are needed")
    limit = max(1, min(int(params.get("limit", 10)), 25))
    ctx.emit(
        "workflow.step", step="discover", message=f"Searching OpenStreetMap: {category} in {city}"
    )
    found = business_discovery.discover(city, category, limit=limit)
    ctx.emit("workflow.step", step="discovered",
             message=f"Found {len(found['businesses'])} {category} in {city}")  # fmt: skip
    created = audited = leads = 0
    audit_errors = 0
    for data in found["businesses"]:
        business, is_new = _upsert_business(ctx.db, data)
        created += is_new
        if business.website:
            try:
                _apply_audit(business, website_auditor.audit_website(business.website))
                audited += 1
                ctx.emit("business.audited", business_id=business.id, name=business.name,
                         score=business.website_score)  # fmt: skip
            except Exception as exc:  # a dead or blocked site is a finding, not a crash
                audit_errors += 1
                log.info("audit failed", extra={"url": business.website, "err": str(exc)})
        if _ensure_lead(ctx.db, business) is not None:
            leads += 1
        ctx.db.commit()
    summary = (
        f"{len(found['businesses'])} businesses found, {audited} websites audited, "
        f"{leads} leads ranked. Website scores are automated estimates."
    )
    ctx.emit("workflow.step", step="done", message=summary)
    return {
        "summary": summary, "found": found["found"], "stored": len(found["businesses"]),
        "new_businesses": created, "audited": audited, "audit_failures": audit_errors,
        "leads": leads, "attribution": found["attribution"],
    }  # fmt: skip


def audit_url(ctx: Context, params: dict[str, Any]) -> dict[str, Any]:
    url = str(params.get("url", "")).strip()
    if not url:
        raise ServiceError("A URL is needed")
    ctx.emit("workflow.step", step="audit", message=f"Auditing {url}")
    audit = website_auditor.audit_website(url)
    if business_id := params.get("business_id"):
        business = ctx.db.get(Business, int(business_id))
        if business is not None:
            _apply_audit(business, audit)
            _ensure_lead(ctx.db, business)
            ctx.db.commit()
    audit["summary"] = f"{audit['url']} scored {audit['website_score']}/100 (estimate)."
    return audit


_HYPE = re.compile(
    r"\b(guarantee[ds]?|100\s?%|risk[- ]free|act now|limited time|last chance|no[. ]?1|#1|"
    r"double your|overnight)\b",
    re.I,
)


def compliance_problems(draft: str) -> list[str]:
    """Anti-spam checks every outreach draft must pass (applied with or without approvals)."""
    problems = []
    if not re.search(r"\bSTOP\b|unsubscribe|opt[- ]?out", draft, re.I):
        problems.append("no opt-out line")
    if not re.search(r"^\s*Subject:", draft, re.I | re.M):
        problems.append("no subject line")
    if hype := _HYPE.findall(draft):
        problems.append("hype or false-urgency wording: " + ", ".join(sorted(set(hype))))
    return problems


def draft_outreach(ctx: Context, params: dict[str, Any]) -> dict[str, Any]:
    """Draft a compliant outreach message for a lead. It is not money, so it needs no approval,
    but it must pass the anti-spam checks; MATT has no email provider, so nothing is sent."""
    lead = ctx.db.get(Lead, int(params.get("lead_id", 0)))
    if lead is None:
        raise NotFoundError("Lead not found")
    b = lead.business
    context = {
        "business": b.name, "category": b.category, "city": b.city, "website": b.website,
        "website_score_estimate": b.website_score,
        "findings": (b.audit or {}).get("findings", [])[:8], "service": lead.service,
    }  # fmt: skip
    objective = (
        "Write a short, honest, personalised B2B email to this business offering the service. "
        "Mention one or two specific findings. No hype, no false claims, no fake urgency, no "
        "promises of results. Include a clear one-line opt-out ('Reply STOP and I won't contact "
        "you again'). Give a subject line first as 'Subject: ...'. "
        "End with the sign-off placeholder [Your name]."
    )
    ctx.emit("workflow.step", step="draft", message=f"Drafting outreach for {b.name}")
    result = runtime.run(ctx.db, ctx.router, _agent(ctx.db, "sales-copywriter"), objective,
                         context=context, task_id=ctx.task_id,
                         override_budget=ctx.override_budget)  # fmt: skip
    lead.outreach_draft = result.text
    problems = compliance_problems(result.text)
    if problems:
        b.outreach_status = "needs_fix"
        lead.next_action = "Draft failed the anti-spam check (" + "; ".join(problems) + ")"
    else:
        b.outreach_status = "ready"
        lead.next_action = (
            "Draft ready. Send it from your own email: MATT has no email provider connected, "
            "so it sends nothing. One message per business; honour any STOP reply."
        )
    events.emit(ctx.db, "outreach.drafted", lead_id=lead.id, status=b.outreach_status)
    ctx.db.commit()
    summary = (
        f"Outreach draft for {b.name} is ready for you to send."
        if not problems
        else f"Outreach draft for {b.name} failed the anti-spam check: {'; '.join(problems)}."
    )
    return {"summary": summary, "draft": result.text, "compliance": problems or "passed"}


_JSON_BLOCK = re.compile(r"\[.*\]", re.S)


def opportunity_research(ctx: Context, params: dict[str, Any]) -> dict[str, Any]:
    """Ask the Opportunity Researcher for candidates, then score them with the formula."""
    focus = str(params.get("focus") or "AI services a solo founder in India can sell")
    objective = (
        f"Propose 5 concrete business opportunities for: {focus}. Return ONLY a JSON array. "
        'Each item: {"title", "category", "description", "evidence" (what this is based '
        "on, say 'model knowledge, unverified' if you have no source), \"factors\": {"
        + ", ".join(f'"{f}"' for f in FACTORS)
        + "} each rated 0-10 (cost, risk and time_to_revenue: higher means worse)}."
    )
    ctx.emit("workflow.step", step="research", message=f"Researching opportunities: {focus}")
    result = runtime.run(ctx.db, ctx.router, _agent(ctx.db, "opportunity-researcher"), objective,
                         task_id=ctx.task_id, override_budget=ctx.override_budget)  # fmt: skip
    match = _JSON_BLOCK.search(result.text)
    try:
        items = json.loads(match.group(0)) if match else []
    except json.JSONDecodeError:
        items = []
    if not isinstance(items, list) or not items:
        raise ServiceError("The model did not return opportunities in the expected format")
    stored = []
    for item in items[:10]:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        factors = {k: float(item.get("factors", {}).get(k, 0) or 0) for k in FACTORS}
        opp = Opportunity(
            title=str(item["title"])[:300], category=str(item.get("category", "other"))[:100],
            description=str(item.get("description", "")), factors=factors,
            score=opportunity_score(factors), truth=Truth.ESTIMATE, status="proposed",
            evidence=str(item.get("evidence") or "model knowledge, unverified"),
            source=f"ai research ({result.routed.spec.model if result.routed else 'model'})",
            task_id=ctx.task_id,
        )  # fmt: skip
        ctx.db.add(opp)
        stored.append(opp)
    ctx.db.commit()
    best = max(stored, key=lambda o: o.score)
    return {"summary": f"{len(stored)} opportunities scored. Top: {best.title} ({best.score}).",
            "opportunity_ids": [o.id for o in stored]}  # fmt: skip


WORKFLOWS: dict[str, tuple[str, Workflow, bool]] = {
    # slug: (description, function, needs an AI model)
    "website_opportunities": (
        "Find local businesses on OpenStreetMap, audit their websites and rank leads.",
        website_opportunities, False,
    ),
    "audit_website": ("Audit one website and score it.", audit_url, False),
    "draft_outreach": (
        "Draft a compliant outreach email for a lead and queue it for your approval.",
        draft_outreach, True,
    ),
    "opportunity_research": (
        "Research and score new business opportunities with the Opportunity Engine formula.",
        opportunity_research, True,
    ),
}  # fmt: skip


def run_workflow(ctx: Context, slug: str, params: dict[str, Any]) -> dict[str, Any]:
    entry = WORKFLOWS.get(slug)
    if entry is None:
        raise NotFoundError(f"Unknown workflow {slug!r}")
    return entry[1](ctx, params)


def daily_report(ctx: Context, params: dict[str, Any]) -> dict[str, Any]:
    """The CEO's daily report: facts from the records, plus recommendations when a model is
    available. Saved to memory so it can be read later."""
    from datetime import timedelta

    from sqlalchemy import func

    from app.core.domain import TaskStatus
    from app.models import Knowledge, Task
    from app.services import earnings

    tz = ctx.router.settings.timezone
    since = datetime.now(UTC) - timedelta(days=1)
    e = earnings.summary(ctx.db, tz, days=1)

    def count(model: Any, *where: Any) -> int:
        return int(ctx.db.scalar(select(func.count()).select_from(model).where(*where)) or 0)

    facts = {
        "date": e["date"],
        "revenue_today_inr": e["today_inr"],
        "revenue_month_inr": e["month_inr"],
        "new_businesses_24h": count(Business, Business.created_at >= since),
        "new_leads_24h": count(Lead, Lead.created_at >= since),
        "leads_total": count(Lead),
        "approvals_pending": count(Approval, Approval.status == ApprovalStatus.PENDING),
        "tasks_done_24h": count(
            Task, Task.status == TaskStatus.SUCCEEDED, Task.finished_at >= since
        ),
        "tasks_failed_24h": count(
            Task, Task.status == TaskStatus.FAILED, Task.finished_at >= since
        ),
        "top_opportunities": [
            f"{o.title} ({o.score:.0f}, estimate)"
            for o in ctx.db.scalars(select(Opportunity).order_by(Opportunity.score.desc()).limit(3))
        ],
    }
    lines = [
        f"CEO report for {facts['date']} (facts from MATT's records)",
        f"- Revenue today {facts['revenue_today_inr']:,.0f} INR, this month "
        f"{facts['revenue_month_inr']:,.0f} INR.",
        f"- Last 24h: {facts['new_businesses_24h']} businesses found, {facts['new_leads_24h']} new "
        f"leads ({facts['leads_total']} total), {facts['tasks_done_24h']} tasks done, "
        f"{facts['tasks_failed_24h']} failed.",
        f"- Waiting for your approval: {facts['approvals_pending']}.",
    ]
    if facts["top_opportunities"]:
        lines.append("- Top opportunities: " + "; ".join(facts["top_opportunities"]) + ".")
    if ctx.router.available:
        ctx.emit("workflow.step", step="report", message="CEO is writing recommendations")
        try:
            result = runtime.run(
                ctx.db, ctx.router, _agent(ctx.db, "ceo"),
                "Using only these facts, give the owner 3 short, concrete RECOMMENDATIONS for "
                "today that move toward the first or next paying customer. No invented numbers.",
                context=facts, task_id=ctx.task_id, override_budget=ctx.override_budget,
            )  # fmt: skip
            lines += ["", "Recommendations:", result.text]
        except NoModelAvailable as exc:
            # The facts still matter: save them so the day has a report and autopilot moves on.
            log.warning("daily report without recommendations: %s", exc)
            lines += ["", f"AI recommendations unavailable this time ({str(exc)[:160]})."]
    else:
        lines += ["", "Add an AI model key for written recommendations."]
    report = "\n".join(lines)
    note = Knowledge(
        kind="report", title=f"CEO report {facts['date']}", content=report,
        tags=["report", "autopilot"], agent_slug="ceo", source="autopilot",
    )  # fmt: skip
    ctx.db.add(note)
    ctx.db.commit()
    ctx.emit("report.ready", knowledge_id=note.id, title=note.title)
    return {"summary": lines[1], "report": report, "knowledge_id": note.id, "facts": facts}


WORKFLOWS["daily_report"] = (
    "Write the CEO's daily report from MATT's records, with recommendations when AI is on.",
    daily_report,
    False,
)


_JSON_OBJECT = re.compile(r"\{.*\}", re.S)
MAX_EXPERIMENT_STEPS = 3


def _bot_facts(ctx: Context, agent: Agent) -> dict[str, Any]:
    from app.services import earnings

    e = earnings.summary(ctx.db, ctx.router.settings.timezone, days=1)
    leads = ctx.db.scalars(
        select(Lead)
        .join(Business)
        .order_by(Business.opportunity_score.desc().nulls_last())
        .limit(5)
    ).all()
    return {
        "revenue_today_inr": e["today_inr"],
        "revenue_month_inr": e["month_inr"],
        "top_leads": [
            f"{lead.business.name} ({lead.business.category}, {lead.business.city}): "
            f"score {lead.business.opportunity_score or 0:.0f}, status {lead.status}"
            for lead in leads
        ],
        "top_opportunities": [
            f"{o.title} ({o.score:.0f}, estimate)"
            for o in ctx.db.scalars(select(Opportunity).order_by(Opportunity.score.desc()).limit(3))
        ],
        "your_skills": agent.capabilities,
        "your_outputs": agent.outputs,
    }


BOT_LIMITS = (
    "Limits: you work only inside MATT. You cannot send messages, publish, sign up for services "
    "or move money; the owner does those. Money only ever comes IN, to the owner's own account. "
    "Use free tools only. Never invent facts or results; label claims FACT, ESTIMATE, "
    "PREDICTION, ASSUMPTION or RECOMMENDATION."
)


def skill_bot(ctx: Context, params: dict[str, Any]) -> dict[str, Any]:
    """One skill works on its own money-making idea.

    With no experiment running, the skill proposes one (a small, legal way to earn money online
    in its field) and records it. Ideas that cost nothing start straight away; any idea that
    needs money waits for the owner in Approvals, the only thing that does. With an experiment
    running, the skill does its next concrete step and saves the work to memory. After a few
    steps it hands the owner what they must do to earn the first rupee. Results count only when
    real revenue is recorded."""
    from decimal import Decimal, InvalidOperation

    from app.models import Experiment, Knowledge

    agent = _agent(ctx.db, str(params["agent_slug"]))
    facts = _bot_facts(ctx, agent)
    running = ctx.db.scalar(
        select(Experiment).where(
            Experiment.agent_slug == agent.slug, Experiment.status == "running"
        )
    )
    if running is None:
        ctx.emit("workflow.step", step="bot", message=f"{agent.name} is proposing its own idea")
        result = runtime.run(
            ctx.db, ctx.router, agent,
            "Propose ONE small, legal experiment in your own field to earn money online for MATT's "
            "owner in India, that you can mostly prepare yourself. Return ONLY a JSON object: "
            '{"name", "hypothesis", "target" (who pays), "plan" (3 short steps you can do), '
            '"needs_money" (true only if it requires spending), "cost_inr" (0 if free), '
            '"expected" (ESTIMATE of revenue and how it is reached)}. ' + BOT_LIMITS,
            context=facts, task_id=ctx.task_id, override_budget=ctx.override_budget, max_tokens=700,
        )  # fmt: skip
        match = _JSON_OBJECT.search(result.text)
        try:
            idea = json.loads(match.group(0)) if match else None
        except json.JSONDecodeError:
            idea = None
        if not isinstance(idea, dict) or not idea.get("name"):
            raise ServiceError(f"{agent.name} did not return an idea in the expected format")
        try:
            cost = max(Decimal(str(idea.get("cost_inr") or 0)), Decimal("0"))
        except InvalidOperation:
            cost = Decimal("0")
        needs_money = bool(idea.get("needs_money")) or cost > 0
        plan = idea.get("plan") or []
        exp = Experiment(
            name=str(idea["name"])[:300], hypothesis=str(idea.get("hypothesis", ""))[:5000],
            target=str(idea.get("target") or "")[:300] or None,
            expected="ESTIMATE: " + str(idea.get("expected") or "unknown")[:4900],
            budget_inr=cost, agent_slug=agent.slug, steps_done=0,
            status="planned" if needs_money else "running",
            decision=("Plan: " + " | ".join(str(p) for p in plan)[:4000]) if plan else None,
        )  # fmt: skip
        ctx.db.add(exp)
        ctx.db.flush()
        if needs_money:
            approval = Approval(
                task_id=ctx.task_id, agent_slug=agent.slug, kind="investment",
                action=f"Invest ₹{cost:,.0f} in '{exp.name}' (proposed by {agent.name})",
                details={"experiment_id": exp.id, "hypothesis": exp.hypothesis,
                         "expected": exp.expected, "plan": plan,
                         "note": "MATT never pays. If you approve, you fund it yourself."},
                estimated_cost_inr=cost, risk_level=RiskLevel.HIGH, status=ApprovalStatus.PENDING,
            )  # fmt: skip
            ctx.db.add(approval)
            events.emit(ctx.db, "approval.requested", action=approval.action)
        events.emit(ctx.db, "experiment.proposed", agent=agent.slug, name=exp.name,
                    needs_money=needs_money)  # fmt: skip
        ctx.db.commit()
        verdict = "waits for your approval (it needs money)" if needs_money else "is running"
        return {"summary": f"{agent.name} proposed '{exp.name}', which {verdict}.",
                "experiment_id": exp.id}  # fmt: skip

    step = running.steps_done + 1
    ctx.emit("workflow.step", step="bot", message=f"{agent.name}: step {step} of '{running.name}'")
    result = runtime.run(
        ctx.db, ctx.router, agent,
        f"You are running your experiment '{running.name}'. Hypothesis: {running.hypothesis}. "
        f"{running.decision or ''} Do step {step} now and produce the actual work product (copy, "
        "offer, list, plan or draft), not a description of it. End with one line: "
        "'NEXT: <your next step>' or, if it is ready, 'OWNER: <exactly what the owner must do "
        "to earn the first rupee>'. " + BOT_LIMITS,
        context=facts, task_id=ctx.task_id, override_budget=ctx.override_budget, max_tokens=900,
    )  # fmt: skip
    note = Knowledge(
        kind="agent", title=f"{agent.name}: {running.name} (step {step})", content=result.text,
        tags=["skill-bot", "experiment", agent.department], agent_slug=agent.slug,
        source="autopilot",
    )  # fmt: skip
    ctx.db.add(note)
    running.steps_done = step
    handoff = re.search(r"^\s*OWNER:\s*(.+)$", result.text, re.M)
    if handoff or step >= MAX_EXPERIMENT_STEPS:
        running.status = "completed"
        running.result = (
            "Prepared by the skill; no revenue counts until you record a real payment. "
            + (f"Your next step: {handoff.group(1).strip()}" if handoff else "See the last step.")
        )[:5000]
    ctx.db.flush()
    events.emit(ctx.db, "experiment.step", agent=agent.slug, name=running.name, step=step)
    ctx.db.commit()
    first = next((ln.strip() for ln in result.text.splitlines() if ln.strip()), "Done")
    return {"summary": f"Step {step} of '{running.name}': {first}"[:300],
            "knowledge_id": note.id, "experiment_id": running.id}  # fmt: skip


WORKFLOWS["skill_bot"] = (
    "Let one skill propose or advance its own money-making experiment (AI model needed).",
    skill_bot,
    True,
)


def code_change(ctx: Context, params: dict[str, Any]) -> dict[str, Any]:
    """Draft an owner's change to MATT's own code; it then waits for approval."""
    from app.services import changes

    ctx.emit("workflow.step", step="draft", message="Drafting the code change")
    row = changes.draft(ctx.db, ctx.router, ctx.router.settings, int(params["change_id"]),
                        ctx.task_id)  # fmt: skip
    if row.status == "failed":
        return {"summary": f"Could not draft change #{row.id}: {row.error}", "change_id": row.id}
    return {"summary": f"Change #{row.id} is drafted and waiting for your approval "
            f"({len(row.files)} file(s)).", "change_id": row.id}  # fmt: skip


def open_change_pr(ctx: Context, params: dict[str, Any]) -> dict[str, Any]:
    """After the owner approves a change, open its pull request (never merged by MATT)."""
    from app.services import changes

    row = changes.open_pr(ctx.db, ctx.router.settings, int(params["change_id"]))
    if row.status == "failed":
        return {"summary": f"Could not open the pull request: {row.error}", "change_id": row.id}
    return {"summary": f"Pull request opened: {row.pr_url}", "change_id": row.id,
            "pr_url": row.pr_url}  # fmt: skip


WORKFLOWS["code_change"] = (
    "Draft an owner-requested change to MATT's own code for approval (AI model needed).",
    code_change,
    True,
)
WORKFLOWS["open_change_pr"] = (
    "Open the pull request for an approved code change. MATT never merges.",
    open_change_pr,
    False,
)
