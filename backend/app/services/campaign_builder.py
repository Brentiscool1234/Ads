"""Campaign creation with the local-business playbook enforced as
validation, not as optional suggestions.
"""

from sqlalchemy.orm import Session

from ..ads.gateway import AdsGateway
from ..models import ClientAccount
from .sync import sync_account

ALLOWED_MATCH_TYPES = {"PHRASE", "EXACT"}


class PlaybookViolation(Exception):
    pass


def build_campaign(db: Session, gateway: AdsGateway, account: ClientAccount,
                   spec: dict, actor: str = "user") -> dict:
    """spec: {name, daily_budget, geo_target_type?, bidding_strategy?,
              ad_groups: [{name, keywords: [{text, match_type, cpc_bid?}]}],
              negatives?: [str]}"""
    errors = []
    if not spec.get("name"):
        errors.append("Campaign name is required.")
    if not spec.get("daily_budget") or float(spec["daily_budget"]) <= 0:
        errors.append("A positive daily budget is required (set once, at creation).")

    for group in spec.get("ad_groups", []):
        for kw in group.get("keywords", []):
            mt = kw.get("match_type", "").upper()
            if mt not in ALLOWED_MATCH_TYPES:
                errors.append(
                    f'Keyword "{kw.get("text")}": match type {mt or "(none)"} not allowed. '
                    "Playbook: phrase or exact only — broad match wastes local budgets."
                )
            kw["match_type"] = mt

    if spec.get("geo_target_type", "PRESENCE") != "PRESENCE":
        errors.append('geo_target_type must be "PRESENCE" for local campaigns.')
    if spec.get("search_partners") or spec.get("display_expansion"):
        errors.append("Search partners / display expansion are off per playbook.")

    if errors:
        raise PlaybookViolation("; ".join(errors))

    spec.setdefault("geo_target_type", "PRESENCE")
    spec.setdefault("bidding_strategy", "MANUAL_CPC")
    # Baseline negatives every local campaign starts with.
    spec.setdefault("negatives", [])
    spec["negatives"] = sorted(set(spec["negatives"]) | {
        "free", "diy", "how to", "jobs", "salary", "school", "training", "cheap",
    })

    result = gateway.create_campaign(account, spec, actor=actor)
    sync_account(db, gateway.client, account)
    return result
