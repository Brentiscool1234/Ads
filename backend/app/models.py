import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Mode(str, enum.Enum):
    REVIEW = "review"        # all engine changes queue for human approval
    AUTOMATIC = "automatic"  # engine applies non-budget changes itself


class ProposalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPLIED = "auto_applied"


class ClientAccount(Base):
    __tablename__ = "client_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    customer_id: Mapped[str] = mapped_column(String(20))  # Google Ads CID
    vertical: Mapped[str] = mapped_column(String(80), default="")  # e.g. plumbing
    service_area: Mapped[str] = mapped_column(String(200), default="")
    target_cpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    mode: Mapped[Mode] = mapped_column(Enum(Mode), default=Mode.REVIEW)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="account")
    proposals: Mapped[list["ChangeProposal"]] = relationship(back_populates="account")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("client_accounts.id"))
    external_id: Mapped[str] = mapped_column(String(40))  # id in Google Ads
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="ENABLED")
    daily_budget: Mapped[float] = mapped_column(Float, default=0)  # read-only mirror
    geo_target_type: Mapped[str] = mapped_column(String(30), default="PRESENCE")
    search_partners: Mapped[bool] = mapped_column(default=False)
    display_expansion: Mapped[bool] = mapped_column(default=False)
    bidding_strategy: Mapped[str] = mapped_column(String(40), default="MANUAL_CPC")
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    account: Mapped[ClientAccount] = relationship(back_populates="campaigns")
    keywords: Mapped[list["Keyword"]] = relationship(back_populates="campaign")
    search_terms: Mapped[list["SearchTerm"]] = relationship(back_populates="campaign")


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    external_id: Mapped[str] = mapped_column(String(40))
    ad_group: Mapped[str] = mapped_column(String(120), default="")
    text: Mapped[str] = mapped_column(String(120))
    match_type: Mapped[str] = mapped_column(String(10))  # EXACT/PHRASE/BROAD
    status: Mapped[str] = mapped_column(String(20), default="ENABLED")
    cpc_bid: Mapped[float] = mapped_column(Float, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0)
    conversions: Mapped[float] = mapped_column(Float, default=0)
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    campaign: Mapped[Campaign] = relationship(back_populates="keywords")


class SearchTerm(Base):
    __tablename__ = "search_terms"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    term: Mapped[str] = mapped_column(String(200))
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0)
    conversions: Mapped[float] = mapped_column(Float, default=0)

    campaign: Mapped[Campaign] = relationship(back_populates="search_terms")


class ChangeProposal(Base):
    __tablename__ = "change_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("client_accounts.id"))
    rule: Mapped[str] = mapped_column(String(60))
    change_type: Mapped[str] = mapped_column(String(40))  # see gateway.CHANGE_TYPES
    entity_ref: Mapped[str] = mapped_column(String(120))  # e.g. keyword:123
    payload: Mapped[dict] = mapped_column(JSON)
    reasoning: Mapped[str] = mapped_column(Text)
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(ProposalStatus), default=ProposalStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    account: Mapped[ClientAccount] = relationship(back_populates="proposals")


class AuditLogEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("client_accounts.id"), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(60))  # "user" or rule name
    change_type: Mapped[str] = mapped_column(String(40))
    entity_ref: Mapped[str] = mapped_column(String(120))
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
