"""Local-business strategy rules.

These encode the playbook in docs/PLAYBOOK.md — deliberately NOT Google's
auto-recommendations. Each rule yields Proposal objects with reasoning a
human can evaluate. Rules must respect the cooldown: never re-touch an
entity changed within settings.cooldown_days.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..config import settings
from ..models import Campaign, ClientAccount, Keyword, SearchTerm

DIY_JOBSEEKER_MARKERS = (
    "how to", "diy", "yourself", "jobs", "job", "salary", "hiring", "school",
    "training", "course", "grants", "free",
)


@dataclass
class Proposal:
    rule: str
    change_type: str
    entity_ref: str
    payload: dict
    reasoning: str
    account_id: int = field(default=0)


def _on_cooldown(kw: Keyword) -> bool:
    if not kw.last_changed_at:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.cooldown_days)
    changed = kw.last_changed_at
    if changed.tzinfo is None:
        changed = changed.replace(tzinfo=timezone.utc)
    return changed > cutoff


def match_type_hygiene(account: ClientAccount, campaign: Campaign):
    """Broad match burns local budgets on irrelevant geography and intent."""
    for kw in campaign.keywords:
        if kw.match_type == "BROAD" and kw.status == "ENABLED" and not _on_cooldown(kw):
            yield Proposal(
                rule="match_type_hygiene",
                change_type="keyword_match_type",
                entity_ref=f"keyword:{kw.id}",
                payload={"match_type": "PHRASE"},
                reasoning=(
                    f'"{kw.text}" is broad match. For a local {account.vertical or "service"} '
                    f"business, broad match lets Google chase loosely related queries far "
                    f"outside buying intent (CTR here: "
                    f"{(kw.clicks / kw.impressions * 100) if kw.impressions else 0:.1f}%, "
                    f"{kw.conversions:g} conversions on ${kw.cost:,.0f}). "
                    f"Convert to phrase match and let the search-terms report drive any expansion."
                ),
            )


def geo_presence(account: ClientAccount, campaign: Campaign):
    """'Presence or interest' shows local ads to people researching the area
    from anywhere; local service buyers are physically in the service area."""
    if campaign.geo_target_type != "PRESENCE":
        yield Proposal(
            rule="geo_presence",
            change_type="campaign_geo_target_type",
            entity_ref=f"campaign:{campaign.id}",
            payload={"geo_target_type": "PRESENCE"},
            reasoning=(
                f'Campaign "{campaign.name}" targets "{campaign.geo_target_type}". '
                "Switch to PRESENCE (people physically in the service area). "
                "Google's default includes anyone showing interest in the area, "
                "which wastes local spend on out-of-area searchers."
            ),
        )


def network_hygiene(account: ClientAccount, campaign: Campaign):
    """Search partners and Display Expansion dilute local search intent."""
    if campaign.search_partners or campaign.display_expansion:
        flags = []
        if campaign.search_partners:
            flags.append("search partners")
        if campaign.display_expansion:
            flags.append("display expansion")
        yield Proposal(
            rule="network_hygiene",
            change_type="campaign_network_settings",
            entity_ref=f"campaign:{campaign.id}",
            payload={"search_partners": False, "display_expansion": False},
            reasoning=(
                f'Campaign "{campaign.name}" has {" and ".join(flags)} enabled. '
                "Both are enabled by default by Google and typically deliver "
                "low-intent clicks for local service campaigns. Turn them off "
                "and keep spend on Google Search proper."
            ),
        )


def negative_miner(account: ClientAccount, campaign: Campaign):
    """Mine the search-terms report for money leaks: DIY/job-seeker intent
    immediately; otherwise require real spend with zero conversions."""
    for st in campaign.search_terms:
        term_l = st.term.lower()
        diy = any(m in term_l for m in DIY_JOBSEEKER_MARKERS)
        wasteful = (st.clicks >= settings.negative_min_clicks
                    and st.conversions == 0
                    and st.cost >= settings.negative_min_cost)
        if st.conversions > 0 and not diy:
            continue
        if diy and st.clicks >= 3:
            yield Proposal(
                rule="negative_miner",
                change_type="negative_keyword_add",
                entity_ref=f"campaign:{campaign.id}",
                payload={"text": st.term, "match_type": "PHRASE"},
                reasoning=(
                    f'Search term "{st.term}" looks like DIY/job-seeker/research intent '
                    f"({st.clicks} clicks, ${st.cost:,.0f}, {st.conversions:g} conv). "
                    "Add as a phrase-match campaign negative."
                ),
            )
        elif wasteful:
            yield Proposal(
                rule="negative_miner",
                change_type="negative_keyword_add",
                entity_ref=f"campaign:{campaign.id}",
                payload={"text": st.term, "match_type": "EXACT"},
                reasoning=(
                    f'Search term "{st.term}" has spent ${st.cost:,.0f} over {st.clicks} '
                    "clicks with zero conversions. Add as an exact-match negative; "
                    "exact only, so close variants that might convert keep serving."
                ),
            )


def bid_adjustments(account: ClientAccount, campaign: Campaign):
    """Small, capped, cooled-down bid moves toward the account's target CPA.
    Only for manual bidding; never touches budget; never moves more than
    settings.max_bid_change_pct in one step."""
    if campaign.bidding_strategy != "MANUAL_CPC" or not account.target_cpa:
        return
    for kw in campaign.keywords:
        if kw.status != "ENABLED" or _on_cooldown(kw) or kw.clicks < 30:
            continue
        if kw.conversions >= 3:
            cpa = kw.cost / kw.conversions
            if cpa < account.target_cpa * 0.7:
                new_bid = round(kw.cpc_bid * (1 + settings.max_bid_change_pct / 100), 2)
                yield Proposal(
                    rule="bid_adjustments",
                    change_type="keyword_bid",
                    entity_ref=f"keyword:{kw.id}",
                    payload={"cpc_bid": new_bid},
                    reasoning=(
                        f'"{kw.text}" converts at ${cpa:,.0f} CPA vs target '
                        f"${account.target_cpa:,.0f} — it can profitably buy more volume. "
                        f"Raise bid {settings.max_bid_change_pct:g}% "
                        f"(${kw.cpc_bid:,.2f} → ${new_bid:,.2f}). Capped and on a "
                        f"{settings.cooldown_days}-day cooldown, so no compounding jumps."
                    ),
                )
            elif cpa > account.target_cpa * 1.5:
                new_bid = round(kw.cpc_bid * (1 - settings.max_bid_change_pct / 100), 2)
                yield Proposal(
                    rule="bid_adjustments",
                    change_type="keyword_bid",
                    entity_ref=f"keyword:{kw.id}",
                    payload={"cpc_bid": new_bid},
                    reasoning=(
                        f'"{kw.text}" converts at ${cpa:,.0f} CPA, well above target '
                        f"${account.target_cpa:,.0f}. Lower bid "
                        f"{settings.max_bid_change_pct:g}% (${kw.cpc_bid:,.2f} → "
                        f"${new_bid:,.2f}) rather than pausing a converting keyword."
                    ),
                )


def pause_nonconverters(account: ClientAccount, campaign: Campaign):
    """Pause only with real evidence — substantial click volume and zero
    conversions. Small samples never justify a pause."""
    for kw in campaign.keywords:
        if (kw.status == "ENABLED" and not _on_cooldown(kw)
                and kw.clicks >= settings.pause_min_clicks and kw.conversions == 0):
            yield Proposal(
                rule="pause_nonconverters",
                change_type="keyword_status",
                entity_ref=f"keyword:{kw.id}",
                payload={"status": "PAUSED"},
                reasoning=(
                    f'"{kw.text}" has {kw.clicks} clicks and ${kw.cost:,.0f} spend with '
                    f"zero conversions — past the {settings.pause_min_clicks}-click "
                    "evidence threshold. Pause (not remove), so it can be revived "
                    "if tracking or landing pages change."
                ),
            )


ALL_RULES = [
    match_type_hygiene,
    geo_presence,
    network_hygiene,
    negative_miner,
    bid_adjustments,
    pause_nonconverters,
]
