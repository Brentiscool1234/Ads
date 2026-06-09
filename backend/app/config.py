from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./localads.db"
    ads_client: str = "mock"  # "mock" or "google" (real API, needs credentials)
    anthropic_api_key: str = ""

    # Strategy guardrails
    cooldown_days: int = 7          # min days between changes to the same entity
    max_bid_change_pct: float = 15  # cap on any single bid adjustment
    negative_min_clicks: int = 8    # search-term clicks w/ 0 conv before proposing a negative
    negative_min_cost: float = 25.0
    pause_min_clicks: int = 80      # clicks w/ 0 conv before proposing a pause

    model_config = SettingsConfigDict(env_prefix="LOCALADS_", env_file=".env")


settings = Settings()
