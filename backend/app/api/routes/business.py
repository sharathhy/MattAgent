"""Business data: discovered businesses, leads, opportunities, customers, products, the
revenue ledger, experiments and memory."""

from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import Admin, CurrentUser, DbSession, Operator
from app.db.base import Base, utcnow
from app.models import (
    Business,
    Customer,
    Experiment,
    Knowledge,
    Lead,
    LedgerEntry,
    Opportunity,
    Product,
)
from app.schemas.business import (
    BusinessOut,
    CustomerIn,
    CustomerOut,
    ExperimentIn,
    ExperimentOut,
    KnowledgeIn,
    KnowledgeOut,
    LeadOut,
    LeadUpdate,
    LedgerIn,
    LedgerOut,
    OpportunityIn,
    OpportunityOut,
    OpportunityUpdate,
    ProductIn,
    ProductOut,
)
from app.schemas.ops import TaskOut
from app.services import audit, events, tasks
from app.services.errors import NotFoundError
from app.services.scoring import opportunity_score

router = APIRouter(tags=["business"])
Limit = Annotated[int, Query(ge=1, le=500)]


def _get[T: Base](db: Session, model: type[T], item_id: int) -> T:
    row = db.get(model, item_id)
    if row is None:
        raise NotFoundError(f"{model.__name__} not found")
    return row


def _save(db: Session, row: Base, user_id: int, action: str, details: dict[str, Any]) -> None:
    db.add(row)
    db.flush()
    audit.record(
        db, actor_type="user", actor_id=str(user_id), action=action,
        target_type=type(row).__tablename__, target_id=str(row.id), details=details,  # type: ignore[attr-defined]
    )  # fmt: skip
    db.commit()


# Businesses -------------------------------------------------------------------------------


@router.get("/businesses", response_model=list[BusinessOut])
def list_businesses(
    db: DbSession, _: CurrentUser, city: str | None = None, category: str | None = None,
    q: str | None = None, limit: Limit = 200,
) -> list[Business]:  # fmt: skip
    stmt = select(Business).order_by(Business.opportunity_score.desc().nulls_last(), Business.id)
    if city:
        stmt = stmt.where(Business.city.ilike(city))
    if category:
        stmt = stmt.where(Business.category == category)
    if q:
        stmt = stmt.where(Business.name.ilike(f"%{q}%"))
    return list(db.scalars(stmt.limit(limit)))


@router.get("/businesses/{item_id}", response_model=BusinessOut)
def get_business(item_id: int, db: DbSession, _: CurrentUser) -> Business:
    return _get(db, Business, item_id)


@router.post("/businesses/{item_id}/audit", response_model=TaskOut, status_code=201)
def audit_business(item_id: int, db: DbSession, user: Operator) -> TaskOut:
    business = _get(db, Business, item_id)
    if not business.website:
        raise NotFoundError("This business has no website on record to audit")
    task = tasks.create(
        db, kind="workflow", created_by=str(user.id), objective=f"Audit {business.name}",
        input={"workflow": "audit_website",
               "params": {"url": business.website, "business_id": business.id}},
    )  # fmt: skip
    return TaskOut.model_validate(task)


@router.delete("/businesses/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business(item_id: int, db: DbSession, user: Admin) -> Response:
    """Delete a business and its lead (data minimisation / opt-out requests)."""
    business = _get(db, Business, item_id)
    lead = db.scalar(select(Lead).where(Lead.business_id == item_id))
    if lead:
        db.delete(lead)
    audit.record(
        db, actor_type="user", actor_id=str(user.id), action="business.deleted",
        target_type="businesses", target_id=str(item_id), details={"name": business.name},
    )  # fmt: skip
    db.delete(business)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Leads ------------------------------------------------------------------------------------


@router.get("/leads", response_model=list[LeadOut])
def list_leads(
    db: DbSession, _: CurrentUser, status: str | None = None, limit: Limit = 200
) -> list[Lead]:
    stmt = (
        select(Lead)
        .join(Business)
        .order_by(Business.opportunity_score.desc().nulls_last(), Lead.id)
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Lead.status == status)
    return list(db.scalars(stmt))


@router.patch("/leads/{item_id}", response_model=LeadOut)
def update_lead(item_id: int, body: LeadUpdate, db: DbSession, user: Operator) -> Lead:
    lead = _get(db, Lead, item_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(lead, key, value)
    if "status" in changes:
        lead.business.lead_status = lead.status
    _save(db, lead, user.id, "lead.updated", {k: str(v) for k, v in changes.items()})
    return lead


@router.post("/leads/{item_id}/draft-outreach", response_model=TaskOut, status_code=201)
def draft_outreach(item_id: int, db: DbSession, user: Operator) -> TaskOut:
    lead = _get(db, Lead, item_id)
    task = tasks.create(
        db, kind="workflow", created_by=str(user.id),
        objective=f"Draft outreach for {lead.business.name}",
        input={"workflow": "draft_outreach", "params": {"lead_id": lead.id}},
    )  # fmt: skip
    return TaskOut.model_validate(task)


# Opportunities ----------------------------------------------------------------------------


@router.get("/opportunities", response_model=list[OpportunityOut])
def list_opportunities(
    db: DbSession, _: CurrentUser, status: str | None = None, limit: Limit = 200
) -> list[Opportunity]:
    stmt = select(Opportunity).order_by(Opportunity.score.desc()).limit(limit)
    if status:
        stmt = stmt.where(Opportunity.status == status)
    return list(db.scalars(stmt))


@router.post("/opportunities", response_model=OpportunityOut, status_code=201)
def create_opportunity(body: OpportunityIn, db: DbSession, user: Operator) -> Opportunity:
    opp = Opportunity(
        **body.model_dump(), score=opportunity_score(body.factors), truth="estimate",
        status="proposed", source=f"user:{user.id}",
    )  # fmt: skip
    _save(db, opp, user.id, "opportunity.created", {"title": opp.title})
    return opp


@router.patch("/opportunities/{item_id}", response_model=OpportunityOut)
def update_opportunity(
    item_id: int, body: OpportunityUpdate, db: DbSession, user: Operator
) -> Opportunity:
    opp = _get(db, Opportunity, item_id)
    if body.status:
        opp.status = body.status
    if body.factors is not None:
        opp.factors = body.factors
        opp.score = opportunity_score(body.factors)
    _save(db, opp, user.id, "opportunity.updated", body.model_dump(exclude_unset=True))
    return opp


# Simple records ---------------------------------------------------------------------------


def _crud(
    path: str,
    model: type[Base],
    schema_in: type[BaseModel],
    schema_out: type[BaseModel],
    order: Any,
) -> None:
    name = model.__tablename__

    @router.get(f"/{path}", response_model=list[schema_out], name=f"list_{name}")  # type: ignore[valid-type]
    def list_items(db: DbSession, _: CurrentUser, limit: Limit = 200) -> list[Any]:
        stmt = select(model).order_by(order).limit(limit)
        if model is Knowledge:
            stmt = stmt.where(or_(Knowledge.expires_at.is_(None), Knowledge.expires_at > utcnow()))
        return list(db.scalars(stmt))

    @router.post(f"/{path}", response_model=schema_out, status_code=201, name=f"create_{name}")
    def create_item(body: schema_in, db: DbSession, user: Operator) -> Any:  # type: ignore[valid-type]
        data = body.model_dump()  # type: ignore[attr-defined]
        if model is Knowledge:
            days = data.pop("retention_days")
            data["expires_at"] = utcnow() + timedelta(days=days) if days else None
            data["source"] = f"user:{user.id}"
        if model is LedgerEntry:
            data["recorded_by"] = str(user.id)
        row = model(**data)
        _save(db, row, user.id, f"{name}.created", {})
        if model is LedgerEntry:
            events.emit(
                db, "ledger.recorded", kind=data["kind"], amount_inr=str(data["amount_inr"])
            )
            db.commit()
        return row

    @router.put(f"/{path}/{{item_id}}", response_model=schema_out, name=f"update_{name}")
    def update_item(item_id: int, body: schema_in, db: DbSession, user: Operator) -> Any:  # type: ignore[valid-type]
        row = _get(db, model, item_id)
        data = body.model_dump()  # type: ignore[attr-defined]
        if model is Knowledge:
            data.pop("retention_days")
        for key, value in data.items():
            setattr(row, key, value)
        _save(db, row, user.id, f"{name}.updated", {})
        return row

    @router.delete(f"/{path}/{{item_id}}", status_code=204, name=f"delete_{name}")
    def delete_item(item_id: int, db: DbSession, user: Admin) -> Response:
        row = _get(db, model, item_id)
        audit.record(
            db, actor_type="user", actor_id=str(user.id), action=f"{name}.deleted",
            target_type=name, target_id=str(item_id),
        )  # fmt: skip
        db.delete(row)
        db.commit()
        return Response(status_code=204)


_crud("customers", Customer, CustomerIn, CustomerOut, Customer.id.desc())
_crud("products", Product, ProductIn, ProductOut, Product.id.desc())
_crud("ledger", LedgerEntry, LedgerIn, LedgerOut, LedgerEntry.occurred_on.desc())
_crud("experiments", Experiment, ExperimentIn, ExperimentOut, Experiment.id.desc())
_crud("knowledge", Knowledge, KnowledgeIn, KnowledgeOut, Knowledge.id.desc())
