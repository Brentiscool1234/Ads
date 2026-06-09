"""The single gateway through which every change to an ads account passes.

Guardrails enforced here, regardless of mode or caller (UI, engine, agent):
- Budget immutability: no change type may touch an existing campaign budget.
  Budgets are set exactly once, at campaign creation, by a human.
- Every applied change is written to the audit log.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import AuditLogEntry, ClientAccount, Keyword
from .base import AdsClient

CHANGE_TYPES = {
    "keyword_match_type",
    "keyword_bid",
    "keyword_status",
    "keyword_add",
    "negative_keyword_add",
    "ad_status",
    "campaign_status",
    "campaign_geo_target_type",
    "campaign_network_settings",
    "campaign_name",
    "ad_schedule",
    "asset_update",
}

# Anything that smells like a budget mutation is rejected outright.
_BUDGET_MARKERS = ("budget",)


class BudgetChangeBlocked(Exception):
    """Raised for any attempted budget mutation. There is no override."""


class UnknownChangeType(Exception):
    pass


def _assert_not_budget(change_type: str, payload: dict):
    if any(m in change_type.lower() for m in _BUDGET_MARKERS):
        raise BudgetChangeBlocked(
            f"Change type '{change_type}' touches budget; budgets are immutable here."
        )
    for key in payload:
        if any(m in key.lower() for m in _BUDGET_MARKERS):
            raise BudgetChangeBlocked(
                f"Payload field '{key}' touches budget; budgets are immutable here."
            )


class AdsGateway:
    def __init__(self, client: AdsClient, db: Session):
        self.client = client
        self.db = db

    def apply(self, account: ClientAccount, change_type: str, entity_ref: str,
              payload: dict, actor: str) -> dict:
        _assert_not_budget(change_type, payload)
        if change_type not in CHANGE_TYPES:
            raise UnknownChangeType(change_type)

        result = self.client.apply_change(
            account.customer_id, change_type, entity_ref, payload
        )
        self._mirror_locally(change_type, entity_ref, payload)
        self.db.add(AuditLogEntry(
            account_id=account.id, actor=actor, change_type=change_type,
            entity_ref=entity_ref, detail={"payload": payload, "result": result},
        ))
        self.db.commit()
        return result

    def create_campaign(self, account: ClientAccount, spec: dict, actor: str) -> dict:
        result = self.client.create_campaign(account.customer_id, spec)
        self.db.add(AuditLogEntry(
            account_id=account.id, actor=actor, change_type="campaign_create",
            entity_ref=f"campaign:{result.get('external_id', '?')}",
            detail={"spec": spec},
        ))
        self.db.commit()
        return result

    def _mirror_locally(self, change_type: str, entity_ref: str, payload: dict):
        """Keep the local cache consistent so cooldowns and the UI see changes."""
        kind, _, raw_id = entity_ref.partition(":")
        if kind == "keyword" and raw_id.isdigit():
            kw = self.db.get(Keyword, int(raw_id))
            if kw:
                if change_type == "keyword_bid" and "cpc_bid" in payload:
                    kw.cpc_bid = float(payload["cpc_bid"])
                elif change_type == "keyword_status" and "status" in payload:
                    kw.status = payload["status"]
                elif change_type == "keyword_match_type" and "match_type" in payload:
                    kw.match_type = payload["match_type"]
                kw.last_changed_at = datetime.now(timezone.utc)
