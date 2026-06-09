from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ads.gateway import AdsGateway, BudgetChangeBlocked
from app.ads.mock import MockAdsClient
from app.db import Base
from app.models import ChangeProposal, ClientAccount, Mode, ProposalStatus
from app.services import proposals as proposal_svc
from app.services.campaign_builder import PlaybookViolation, build_campaign
from app.services.sync import sync_account
from app.strategy.engine import run_engine


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def setup(db):
    client = MockAdsClient()
    account = ClientAccount(name="Reyes Plumbing", customer_id="111-222-3333",
                            vertical="plumbing", target_cpa=80.0)
    db.add(account)
    db.commit()
    gateway = AdsGateway(client, db)
    return db, client, account, gateway


def test_budget_change_blocked_by_change_type(setup):
    db, client, account, gateway = setup
    with pytest.raises(BudgetChangeBlocked):
        gateway.apply(account, "campaign_budget", "campaign:1",
                      {"daily_budget": 999}, actor="user")
    assert client.applied == []


def test_budget_change_blocked_by_payload_field(setup):
    db, client, account, gateway = setup
    with pytest.raises(BudgetChangeBlocked):
        gateway.apply(account, "campaign_network_settings", "campaign:1",
                      {"search_partners": False, "daily_budget_micros": 5}, actor="user")
    assert client.applied == []


def test_review_mode_queues_without_applying(setup):
    db, client, account, gateway = setup
    sync_account(db, client, account)
    pending = db.query(ChangeProposal).filter_by(
        account_id=account.id, status=ProposalStatus.PENDING).all()
    assert pending, "engine should find issues in seeded data"
    # nothing applied to the ads backend in review mode
    assert client.applied == []
    rules = {p.rule for p in pending}
    assert "match_type_hygiene" in rules   # seeded BROAD keyword
    assert "geo_presence" in rules         # seeded PRESENCE_OR_INTEREST
    assert "network_hygiene" in rules      # seeded search_partners=True
    assert "negative_miner" in rules       # seeded DIY/job search terms


def test_automatic_mode_applies_but_never_budget(setup):
    db, client, account, gateway = setup
    account.mode = Mode.AUTOMATIC
    db.commit()
    sync_account(db, client, account)
    applied = db.query(ChangeProposal).filter_by(
        account_id=account.id, status=ProposalStatus.AUTO_APPLIED).all()
    assert applied
    assert len(client.applied) == len(applied)
    assert all("budget" not in a["change_type"] for a in client.applied)
    assert all("budget" not in k.lower()
               for a in client.applied for k in a["payload"])


def test_approve_applies_and_reject_does_not(setup):
    db, client, account, gateway = setup
    sync_account(db, client, account)
    p1, p2 = db.query(ChangeProposal).filter_by(account_id=account.id).limit(2).all()
    proposal_svc.approve(db, gateway, p1.id)
    assert p1.status == ProposalStatus.APPROVED
    assert len(client.applied) == 1
    proposal_svc.reject(db, p2.id)
    assert p2.status == ProposalStatus.REJECTED
    assert len(client.applied) == 1  # unchanged
    with pytest.raises(proposal_svc.ProposalError):
        proposal_svc.approve(db, gateway, p2.id)  # can't approve a rejected one


def test_engine_does_not_duplicate_pending_proposals(setup):
    db, client, account, gateway = setup
    sync_account(db, client, account)
    first = db.query(ChangeProposal).count()
    sync_account(db, client, account)
    assert db.query(ChangeProposal).count() == first


def test_cooldown_blocks_repeat_changes(setup):
    db, client, account, gateway = setup
    sync_account(db, client, account)
    p = db.query(ChangeProposal).filter_by(rule="match_type_hygiene").first()
    proposal_svc.approve(db, gateway, p.id)
    # keyword now has last_changed_at = now; engine must skip it
    run_engine(db, gateway, account)
    fresh = db.query(ChangeProposal).filter_by(
        rule="match_type_hygiene", entity_ref=p.entity_ref,
        status=ProposalStatus.PENDING).count()
    assert fresh == 0


def test_campaign_builder_rejects_broad_match(setup):
    db, client, account, gateway = setup
    spec = {"name": "Test", "daily_budget": 40,
            "ad_groups": [{"name": "G", "keywords":
                           [{"text": "plumber", "match_type": "BROAD"}]}]}
    with pytest.raises(PlaybookViolation, match="broad match"):
        build_campaign(db, gateway, account, spec)


def test_campaign_builder_applies_playbook_defaults(setup):
    db, client, account, gateway = setup
    spec = {"name": "Drain Cleaning - Springfield", "daily_budget": 40,
            "ad_groups": [{"name": "Drains", "keywords":
                           [{"text": "drain cleaning", "match_type": "PHRASE"}]}]}
    result = build_campaign(db, gateway, account, spec)
    assert result["ok"]
    created = [c for c in client.fetch_campaigns(account.customer_id)
               if c["external_id"] == result["external_id"]][0]
    assert created["geo_target_type"] == "PRESENCE"
    assert created["search_partners"] is False
    assert created["status"] == "PAUSED"  # human enables after final review
