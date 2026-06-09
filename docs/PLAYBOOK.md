# Local Business Ads Playbook

This is what the strategy engine is "taught." Every rule in
`backend/app/strategy/rules.py` maps to a section here. Edit this document and
the rules together — the playbook is the spec, the rules are the implementation.
This is deliberately **not** Google's recommended setup; Google's defaults and
auto-applied recommendations optimize for spend, not for a local service
business's cost per lead.

## 1. Match types: phrase + exact only — no broad match
Broad match lets Google expand to "related" queries. For a plumber in
Springfield that means informational queries, DIY searches, and out-of-area
traffic. Search volume for local services is modest enough that phrase + exact
covers real demand. Expansion comes from the search-terms report: when a query
converts, promote it to a keyword — never by loosening match types.
**Rule:** `match_type_hygiene` — proposes converting BROAD keywords to PHRASE.

## 2. Geo targeting: presence, not interest
Google's default ("Presence or interest") shows ads to anyone *interested in*
the area — people researching from anywhere. Local service buyers are
physically in the service area when they search.
**Rule:** `geo_presence` — flags campaigns not set to PRESENCE.

## 3. Networks: Google Search only
Search partners and Display Expansion are on by default and deliver low-intent
clicks for local services. Off, always.
**Rule:** `network_hygiene`.

## 4. Negative keywords: mine the search-terms report continuously
Two triggers:
- **Intent markers** (immediate): "how to", "diy", "jobs", "salary", "school",
  "free", "grants" — added as phrase negatives after a handful of clicks.
- **Spend evidence**: a term with meaningful spend and zero conversions gets an
  *exact* negative, so close variants that might convert keep serving.
Every new campaign starts with a baseline negative list (jobs/DIY/free/cheap).
**Rule:** `negative_miner`; baseline list in `campaign_builder`.

## 5. Bidding: manual first, automate only with data
Start campaigns on manual CPC. Google's smart bidding needs ~30 conversions a
month to perform; before that it overspends learning. Bid moves are capped at
15% per step with a 7-day cooldown per entity — direction over speed, never
oscillating.
**Rule:** `bid_adjustments` (only acts when the account has a target CPA and
the keyword has ≥30 clicks and ≥3 conversions).

## 6. Pause on evidence, not impatience
A keyword is only proposed for pausing after ~80 clicks with zero conversions.
Small samples prove nothing; pausing early kills keywords that just haven't
had volume yet. Pause, never remove — keep the history.
**Rule:** `pause_nonconverters`.

## 7. Google recommendations: never auto-applied
Auto-apply is Google optimizing its own revenue. Recommendations are surfaced
for human information only. (When the real API client lands, the tool will
also dismiss "auto-apply" enrollment.)

## 8. Budgets are sacred
The tool can never change a budget — not in review mode, not in automatic
mode, not via the agent. Enforced in `ads/gateway.py` with no override path.
Budgets are set once at campaign creation by a human and changed only by a
human in the Google Ads UI.

## 9. New campaigns start paused
The builder creates campaigns PAUSED. A human reviews structure, ads, and
tracking, then enables.

## Tuning knobs
All thresholds are env-configurable (`backend/app/config.py`):
`LOCALADS_COOLDOWN_DAYS` (7), `LOCALADS_MAX_BID_CHANGE_PCT` (15),
`LOCALADS_NEGATIVE_MIN_CLICKS` (8), `LOCALADS_NEGATIVE_MIN_COST` (25),
`LOCALADS_PAUSE_MIN_CLICKS` (80).
