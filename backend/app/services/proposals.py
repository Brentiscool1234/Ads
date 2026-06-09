from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..ads.gateway import AdsGateway
from ..models import ChangeProposal, ProposalStatus


class ProposalError(Exception):
    pass


def _get_pending(db: Session, proposal_id: int) -> ChangeProposal:
    p = db.get(ChangeProposal, proposal_id)
    if not p:
        raise ProposalError(f"Proposal {proposal_id} not found.")
    if p.status != ProposalStatus.PENDING:
        raise ProposalError(f"Proposal {proposal_id} is already {p.status.value}.")
    return p


def approve(db: Session, gateway: AdsGateway, proposal_id: int,
            edited_payload: dict | None = None) -> ChangeProposal:
    p = _get_pending(db, proposal_id)
    if edited_payload is not None:
        p.payload = edited_payload
    gateway.apply(p.account, p.change_type, p.entity_ref, p.payload,
                  actor=f"user(approved:{p.rule})")
    p.status = ProposalStatus.APPROVED
    p.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return p


def reject(db: Session, proposal_id: int) -> ChangeProposal:
    p = _get_pending(db, proposal_id)
    p.status = ProposalStatus.REJECTED
    p.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return p
