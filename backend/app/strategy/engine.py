"""Runs the rule set over an account's cached data and either queues
proposals (review mode) or applies them through the gateway (automatic
mode). Budgets cannot be touched in either mode — the gateway hard-blocks
them, and no rule produces budget changes in the first place.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..ads.gateway import AdsGateway
from ..models import ChangeProposal, ClientAccount, Mode, ProposalStatus
from .rules import ALL_RULES


def _already_pending(db: Session, account: ClientAccount, p) -> bool:
    return db.query(ChangeProposal).filter_by(
        account_id=account.id, change_type=p.change_type,
        entity_ref=p.entity_ref, status=ProposalStatus.PENDING,
    ).count() > 0


def run_engine(db: Session, gateway: AdsGateway, account: ClientAccount) -> dict:
    queued, applied = [], []
    for campaign in account.campaigns:
        for rule in ALL_RULES:
            for p in rule(account, campaign):
                if _already_pending(db, account, p):
                    continue
                proposal = ChangeProposal(
                    account_id=account.id, rule=p.rule, change_type=p.change_type,
                    entity_ref=p.entity_ref, payload=p.payload, reasoning=p.reasoning,
                )
                if account.mode == Mode.AUTOMATIC:
                    gateway.apply(account, p.change_type, p.entity_ref,
                                  p.payload, actor=f"rule:{p.rule}")
                    proposal.status = ProposalStatus.AUTO_APPLIED
                    proposal.resolved_at = datetime.now(timezone.utc)
                    applied.append(proposal)
                else:
                    queued.append(proposal)
                db.add(proposal)
    db.commit()
    return {"queued": len(queued), "auto_applied": len(applied)}
