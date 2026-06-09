"""Ads client interface.

Two implementations:
- MockAdsClient: seeded, in-memory data for development and testing.
- GoogleAdsClientImpl (future): real Google Ads API via the google-ads
  library, once a developer token is approved. It must implement this
  same interface so nothing above the gateway changes.
"""

from abc import ABC, abstractmethod


class AdsClient(ABC):
    @abstractmethod
    def fetch_campaigns(self, customer_id: str) -> list[dict]: ...

    @abstractmethod
    def fetch_keywords(self, customer_id: str, campaign_external_id: str) -> list[dict]: ...

    @abstractmethod
    def fetch_search_terms(self, customer_id: str, campaign_external_id: str) -> list[dict]: ...

    @abstractmethod
    def apply_change(self, customer_id: str, change_type: str, entity_ref: str,
                     payload: dict) -> dict:
        """Execute a single mutate. Returns the API result summary."""

    @abstractmethod
    def create_campaign(self, customer_id: str, spec: dict) -> dict:
        """Create a campaign (the only moment a budget may be set)."""
