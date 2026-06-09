import csv
import io
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import AuditLogEntry, ClientAccount
from ..strategy.rules import ALL_RULES


def performance_csv(account: ClientAccount) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["campaign", "ad_group", "keyword", "match_type", "status",
                "cpc_bid", "clicks", "impressions", "ctr_pct", "cost",
                "conversions", "cpa"])
    for c in account.campaigns:
        for k in c.keywords:
            ctr = (k.clicks / k.impressions * 100) if k.impressions else 0
            cpa = (k.cost / k.conversions) if k.conversions else ""
            w.writerow([c.name, k.ad_group, k.text, k.match_type, k.status,
                        f"{k.cpc_bid:.2f}", k.clicks, k.impressions, f"{ctr:.2f}",
                        f"{k.cost:.2f}", f"{k.conversions:g}",
                        f"{cpa:.2f}" if cpa != "" else ""])
    return buf.getvalue()


def audit_markdown(db: Session, account: ClientAccount) -> str:
    """A client-facing account audit: current findings from every rule,
    plus the recent change history."""
    lines = [
        f"# Account Audit — {account.name}",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · "
        f"Mode: {account.mode.value} · Vertical: {account.vertical or '—'}",
        "",
        "## Findings",
    ]
    findings = 0
    for campaign in account.campaigns:
        for rule in ALL_RULES:
            for p in rule(account, campaign):
                findings += 1
                lines.append(f"- **[{p.rule}]** {p.reasoning}")
    if not findings:
        lines.append("- No open findings. Account conforms to the playbook.")

    lines += ["", "## Recent changes (last 25)"]
    entries = (db.query(AuditLogEntry).filter_by(account_id=account.id)
               .order_by(AuditLogEntry.created_at.desc()).limit(25).all())
    if not entries:
        lines.append("- No changes recorded yet.")
    for e in entries:
        lines.append(f"- {e.created_at:%Y-%m-%d %H:%M} · {e.actor} · "
                     f"{e.change_type} on {e.entity_ref}")
    return "\n".join(lines) + "\n"
