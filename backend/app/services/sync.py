"""Pulls fresh data from the ads backend into the local cache, then runs
the strategy engine. This is what the scheduler (or the Sync button) calls.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..ads.base import AdsClient
from ..ads.gateway import AdsGateway
from ..models import Campaign, ClientAccount, Keyword, SearchTerm
from ..strategy.engine import run_engine


def sync_account(db: Session, client: AdsClient, account: ClientAccount) -> dict:
    for c_data in client.fetch_campaigns(account.customer_id):
        campaign = db.query(Campaign).filter_by(
            account_id=account.id, external_id=c_data["external_id"]).first()
        if not campaign:
            campaign = Campaign(account_id=account.id,
                                external_id=c_data["external_id"], name=c_data["name"])
            db.add(campaign)
            db.flush()
        for f in ("name", "status", "daily_budget", "geo_target_type",
                  "search_partners", "display_expansion", "bidding_strategy"):
            setattr(campaign, f, c_data[f])
        campaign.synced_at = datetime.now(timezone.utc)

        existing_kw = {k.external_id: k for k in campaign.keywords}
        for k_data in client.fetch_keywords(account.customer_id, campaign.external_id):
            kw = existing_kw.get(k_data["external_id"])
            if not kw:
                kw = Keyword(campaign_id=campaign.id, external_id=k_data["external_id"])
                db.add(kw)
            for f in ("ad_group", "text", "match_type", "status", "cpc_bid",
                      "clicks", "impressions", "cost", "conversions"):
                setattr(kw, f, k_data[f])

        db.query(SearchTerm).filter_by(campaign_id=campaign.id).delete()
        for t_data in client.fetch_search_terms(account.customer_id, campaign.external_id):
            db.add(SearchTerm(campaign_id=campaign.id, **t_data))

    db.commit()
    db.refresh(account)
    engine_result = run_engine(db, AdsGateway(client, db), account)
    return {"synced": True, **engine_result}
