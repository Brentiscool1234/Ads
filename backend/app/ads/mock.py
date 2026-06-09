"""Mock ads backend with realistic seeded data for two local businesses.

Lets the whole tool run end-to-end (sync, strategy engine, proposals,
approvals, reports) before real API credentials exist.
"""

import itertools
import random

from .base import AdsClient

_ids = itertools.count(1000)


def _kw(ad_group, text, match, bid, clicks, imps, cost, conv):
    return {
        "external_id": str(next(_ids)), "ad_group": ad_group, "text": text,
        "match_type": match, "status": "ENABLED", "cpc_bid": bid,
        "clicks": clicks, "impressions": imps, "cost": cost, "conversions": conv,
    }


def _term(term, clicks, cost, conv):
    return {"term": term, "clicks": clicks, "cost": cost, "conversions": conv}


SEED = {
    "111-222-3333": {  # Reyes Plumbing
        "campaigns": [{
            "external_id": "c-plumb-1",
            "name": "Plumbing - Emergency - Springfield",
            "status": "ENABLED", "daily_budget": 60.0,
            "geo_target_type": "PRESENCE_OR_INTEREST",  # rule should flag this
            "search_partners": True,                     # and this
            "display_expansion": False,
            "bidding_strategy": "MANUAL_CPC",
            "keywords": [
                _kw("Emergency", "emergency plumber", "PHRASE", 8.5, 210, 3400, 1620.0, 22),
                _kw("Emergency", "plumber near me", "BROAD", 7.0, 180, 5200, 1310.0, 9),
                _kw("Emergency", "burst pipe repair", "EXACT", 9.0, 64, 800, 540.0, 8),
                _kw("Water Heater", "water heater replacement", "PHRASE", 6.5, 95, 1500, 590.0, 11),
                _kw("Water Heater", "tankless water heater cost", "PHRASE", 5.0, 88, 2100, 410.0, 0),
            ],
            "search_terms": [
                _term("emergency plumber springfield", 85, 690.0, 12),
                _term("how to fix leaky faucet myself", 22, 96.0, 0),
                _term("plumber jobs springfield", 14, 52.0, 0),
                _term("free plumbing estimate", 9, 38.0, 1),
                _term("burst pipe repair near me", 31, 270.0, 5),
            ],
        }],
    },
    "444-555-6666": {  # Bright Smile Dental
        "campaigns": [{
            "external_id": "c-dental-1",
            "name": "Dental - Implants - Metro",
            "status": "ENABLED", "daily_budget": 90.0,
            "geo_target_type": "PRESENCE",
            "search_partners": False, "display_expansion": True,  # flag
            "bidding_strategy": "MAXIMIZE_CONVERSIONS",
            "keywords": [
                _kw("Implants", "dental implants", "PHRASE", 11.0, 320, 6100, 3460.0, 18),
                _kw("Implants", "teeth implants cost", "PHRASE", 9.0, 150, 2900, 1280.0, 6),
                _kw("Implants", "dentist", "BROAD", 6.0, 240, 9800, 1390.0, 3),
                _kw("Whitening", "teeth whitening near me", "PHRASE", 4.5, 130, 2400, 560.0, 9),
            ],
            "search_terms": [
                _term("dental implant grants", 41, 350.0, 0),
                _term("dental assistant school", 18, 92.0, 0),
                _term("cheap dentist no insurance", 26, 140.0, 1),
                _term("dental implants metro city", 64, 710.0, 9),
            ],
        }],
    },
}


class MockAdsClient(AdsClient):
    def __init__(self):
        # deep-ish copy so mutations don't bleed across tests
        self.data = {
            cid: {"campaigns": [
                {**c, "keywords": [dict(k) for k in c["keywords"]],
                 "search_terms": [dict(t) for t in c["search_terms"]]}
                for c in acct["campaigns"]
            ]} for cid, acct in SEED.items()
        }
        self.applied: list[dict] = []  # record of mutates, useful in tests

    def _campaigns(self, customer_id):
        return self.data.get(customer_id, {"campaigns": []})["campaigns"]

    def fetch_campaigns(self, customer_id):
        return [{k: v for k, v in c.items() if k not in ("keywords", "search_terms")}
                for c in self._campaigns(customer_id)]

    def fetch_keywords(self, customer_id, campaign_external_id):
        for c in self._campaigns(customer_id):
            if c["external_id"] == campaign_external_id:
                return [dict(k) for k in c["keywords"]]
        return []

    def fetch_search_terms(self, customer_id, campaign_external_id):
        for c in self._campaigns(customer_id):
            if c["external_id"] == campaign_external_id:
                return [dict(t) for t in c["search_terms"]]
        return []

    def apply_change(self, customer_id, change_type, entity_ref, payload):
        self.applied.append({
            "customer_id": customer_id, "change_type": change_type,
            "entity_ref": entity_ref, "payload": payload,
        })
        return {"ok": True, "mock": True}

    def create_campaign(self, customer_id, spec):
        ext_id = f"c-new-{random.randint(1000, 9999)}"
        campaign = {
            "external_id": ext_id, "name": spec["name"], "status": "PAUSED",
            "daily_budget": spec["daily_budget"],
            "geo_target_type": spec.get("geo_target_type", "PRESENCE"),
            "search_partners": False, "display_expansion": False,
            "bidding_strategy": spec.get("bidding_strategy", "MANUAL_CPC"),
            "keywords": [
                _kw(g["name"], kw["text"], kw["match_type"], kw.get("cpc_bid", 2.0),
                    0, 0, 0.0, 0)
                for g in spec.get("ad_groups", []) for kw in g.get("keywords", [])
            ],
            "search_terms": [],
        }
        self.data.setdefault(customer_id, {"campaigns": []})["campaigns"].append(campaign)
        return {"external_id": ext_id, "ok": True}
