from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .ads.gateway import AdsGateway, BudgetChangeBlocked, UnknownChangeType
from .ads.mock import MockAdsClient
from .config import settings
from .db import get_db
from .models import (AuditLogEntry, Campaign, ChangeProposal, ClientAccount,
                     Mode, ProposalStatus)
from .services import proposals as proposal_svc
from .services.campaign_builder import PlaybookViolation, build_campaign
from .services.reports import audit_markdown, performance_csv
from .services.sync import sync_account

router = APIRouter(prefix="/api")

# One shared client instance: the mock keeps in-memory state across requests.
# Swapped for the real Google Ads client via LOCALADS_ADS_CLIENT=google.
_ads_client = MockAdsClient()


def get_client():
    if settings.ads_client == "google":
        raise HTTPException(501, "Real Google Ads client not configured yet "
                                 "(waiting on developer token).")
    return _ads_client


def _account_or_404(db: Session, account_id: int) -> ClientAccount:
    account = db.get(ClientAccount, account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    return account


# ---------- accounts ----------

class AccountIn(BaseModel):
    name: str
    customer_id: str
    vertical: str = ""
    service_area: str = ""
    target_cpa: float | None = None
    mode: Mode = Mode.REVIEW


class AccountPatch(BaseModel):
    name: str | None = None
    vertical: str | None = None
    service_area: str | None = None
    target_cpa: float | None = None
    mode: Mode | None = None


def _account_out(db: Session, a: ClientAccount) -> dict:
    pending = db.query(ChangeProposal).filter_by(
        account_id=a.id, status=ProposalStatus.PENDING).count()
    spend = sum(k.cost for c in a.campaigns for k in c.keywords)
    conv = sum(k.conversions for c in a.campaigns for k in c.keywords)
    return {"id": a.id, "name": a.name, "customer_id": a.customer_id,
            "vertical": a.vertical, "service_area": a.service_area,
            "target_cpa": a.target_cpa, "mode": a.mode.value,
            "campaigns": len(a.campaigns), "pending_proposals": pending,
            "total_cost": round(spend, 2), "total_conversions": conv}


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    return [_account_out(db, a) for a in db.query(ClientAccount).all()]


@router.post("/accounts")
def create_account(body: AccountIn, db: Session = Depends(get_db)):
    account = ClientAccount(**body.model_dump())
    db.add(account)
    db.commit()
    return _account_out(db, account)


@router.patch("/accounts/{account_id}")
def update_account(account_id: int, body: AccountPatch, db: Session = Depends(get_db)):
    account = _account_or_404(db, account_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(account, k, v)
    db.commit()
    return _account_out(db, account)


@router.post("/accounts/{account_id}/sync")
def sync(account_id: int, db: Session = Depends(get_db), client=Depends(get_client)):
    account = _account_or_404(db, account_id)
    return sync_account(db, client, account)


# ---------- campaigns ----------

@router.get("/accounts/{account_id}/campaigns")
def list_campaigns(account_id: int, db: Session = Depends(get_db)):
    account = _account_or_404(db, account_id)
    return [{
        "id": c.id, "external_id": c.external_id, "name": c.name,
        "status": c.status, "daily_budget": c.daily_budget,
        "geo_target_type": c.geo_target_type, "search_partners": c.search_partners,
        "display_expansion": c.display_expansion,
        "bidding_strategy": c.bidding_strategy,
        "keywords": [{
            "id": k.id, "ad_group": k.ad_group, "text": k.text,
            "match_type": k.match_type, "status": k.status, "cpc_bid": k.cpc_bid,
            "clicks": k.clicks, "impressions": k.impressions, "cost": k.cost,
            "conversions": k.conversions,
        } for k in c.keywords],
        "search_terms": [{
            "term": t.term, "clicks": t.clicks, "cost": t.cost,
            "conversions": t.conversions,
        } for t in c.search_terms],
    } for c in account.campaigns]


class ChangeIn(BaseModel):
    change_type: str
    entity_ref: str
    payload: dict


@router.post("/accounts/{account_id}/changes")
def apply_change(account_id: int, body: ChangeIn, db: Session = Depends(get_db),
                 client=Depends(get_client)):
    """Direct human edit (review mode included) — budget still hard-blocked."""
    account = _account_or_404(db, account_id)
    gateway = AdsGateway(client, db)
    try:
        return gateway.apply(account, body.change_type, body.entity_ref,
                             body.payload, actor="user")
    except BudgetChangeBlocked as e:
        raise HTTPException(403, str(e))
    except UnknownChangeType as e:
        raise HTTPException(400, f"Unknown change type: {e}")


@router.post("/accounts/{account_id}/campaigns")
def create_campaign(account_id: int, spec: dict, db: Session = Depends(get_db),
                    client=Depends(get_client)):
    account = _account_or_404(db, account_id)
    try:
        return build_campaign(db, AdsGateway(client, db), account, spec)
    except PlaybookViolation as e:
        raise HTTPException(422, str(e))


# ---------- proposals ----------

@router.get("/accounts/{account_id}/proposals")
def list_proposals(account_id: int, status: str = "pending",
                   db: Session = Depends(get_db)):
    q = db.query(ChangeProposal).filter_by(account_id=account_id)
    if status != "all":
        q = q.filter_by(status=ProposalStatus(status))
    return [{
        "id": p.id, "rule": p.rule, "change_type": p.change_type,
        "entity_ref": p.entity_ref, "payload": p.payload,
        "reasoning": p.reasoning, "status": p.status.value,
        "created_at": p.created_at.isoformat(),
    } for p in q.order_by(ChangeProposal.created_at.desc()).all()]


class ApproveIn(BaseModel):
    payload: dict | None = None  # optionally edited before approval


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: int, body: ApproveIn,
                     db: Session = Depends(get_db), client=Depends(get_client)):
    try:
        p = proposal_svc.approve(db, AdsGateway(client, db), proposal_id, body.payload)
    except proposal_svc.ProposalError as e:
        raise HTTPException(409, str(e))
    except BudgetChangeBlocked as e:
        raise HTTPException(403, str(e))
    return {"id": p.id, "status": p.status.value}


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, db: Session = Depends(get_db)):
    try:
        p = proposal_svc.reject(db, proposal_id)
    except proposal_svc.ProposalError as e:
        raise HTTPException(409, str(e))
    return {"id": p.id, "status": p.status.value}


# ---------- reports & audit ----------

@router.get("/accounts/{account_id}/report.csv")
def report_csv(account_id: int, db: Session = Depends(get_db)):
    account = _account_or_404(db, account_id)
    return Response(performance_csv(account), media_type="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="{account.name}-report.csv"'})


@router.get("/accounts/{account_id}/audit.md", response_class=PlainTextResponse)
def audit_md(account_id: int, db: Session = Depends(get_db)):
    account = _account_or_404(db, account_id)
    return audit_markdown(db, account)


@router.get("/audit-log")
def audit_log(account_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(AuditLogEntry)
    if account_id:
        q = q.filter_by(account_id=account_id)
    return [{
        "id": e.id, "account_id": e.account_id, "actor": e.actor,
        "change_type": e.change_type, "entity_ref": e.entity_ref,
        "detail": e.detail, "created_at": e.created_at.isoformat(),
    } for e in q.order_by(AuditLogEntry.created_at.desc()).limit(200).all()]
