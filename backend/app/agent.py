"""Agent chat endpoint.

Natural-language layer over the same guarded internals as the dashboard:
- every change goes through AdsGateway (budgets hard-blocked),
- in review mode the agent's changes land in the proposal queue,
- in automatic mode they apply and are audit-logged.

Requires LOCALADS_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY). The manual
tool loop is deliberate: it lets us route tool execution through the
gateway instead of letting the SDK auto-execute.
"""

import json

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .ads.gateway import AdsGateway, BudgetChangeBlocked
from .config import settings
from .db import get_db
from .models import ChangeProposal, ClientAccount, Mode, ProposalStatus
from .services.campaign_builder import PlaybookViolation, build_campaign
from .services.reports import audit_markdown
from .services.sync import sync_account

router = APIRouter(prefix="/api/agent")

MODEL = "claude-opus-4-8"

SYSTEM = """You are the assistant inside LocalAds Manager, an internal tool an \
agency uses to run Google Ads for local businesses. You help account managers \
audit accounts, draft campaigns, and queue optimizations.

Operating rules (enforced by the system, but act accordingly):
- You can NEVER change a campaign budget. Don't offer to.
- Strategy playbook: phrase/exact match only (broad match wastes local budgets), \
geo targeting set to PRESENCE, search partners and display expansion off, \
negative keywords mined from search terms, evidence thresholds before pausing \
anything, capped bid moves with cooldowns. Never recommend auto-applying \
Google's recommendations.
- In review mode your changes become pending proposals for the human to \
approve; say so when you queue one.
Keep replies short and concrete."""

TOOLS = [
    {"name": "list_accounts",
     "description": "List all client accounts with id, name, vertical, mode, "
                    "campaign count and pending proposal count.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_account_data",
     "description": "Get campaigns, keywords and search terms for one account. "
                    "Call list_accounts first to get the account id.",
     "input_schema": {"type": "object",
                      "properties": {"account_id": {"type": "integer"}},
                      "required": ["account_id"]}},
    {"name": "audit_account",
     "description": "Run the full strategy audit for an account; returns a "
                    "markdown report of findings and recent changes.",
     "input_schema": {"type": "object",
                      "properties": {"account_id": {"type": "integer"}},
                      "required": ["account_id"]}},
    {"name": "sync_account",
     "description": "Pull fresh data and run the strategy engine. In review "
                    "mode this queues proposals; in automatic mode it applies them.",
     "input_schema": {"type": "object",
                      "properties": {"account_id": {"type": "integer"}},
                      "required": ["account_id"]}},
    {"name": "queue_change",
     "description": "Queue (review mode) or apply (automatic mode) a single "
                    "non-budget change. change_type is one of: keyword_match_type, "
                    "keyword_bid, keyword_status, negative_keyword_add, ad_status, "
                    "campaign_status, campaign_geo_target_type, "
                    "campaign_network_settings, ad_schedule. entity_ref like "
                    "'keyword:12' or 'campaign:3' using local ids from get_account_data.",
     "input_schema": {"type": "object",
                      "properties": {"account_id": {"type": "integer"},
                                     "change_type": {"type": "string"},
                                     "entity_ref": {"type": "string"},
                                     "payload": {"type": "object"},
                                     "reasoning": {"type": "string"}},
                      "required": ["account_id", "change_type", "entity_ref",
                                   "payload", "reasoning"]}},
    {"name": "create_campaign",
     "description": "Create a new search campaign (created PAUSED for human "
                    "review; playbook validation enforced — phrase/exact only). "
                    "spec: {name, daily_budget, ad_groups:[{name, keywords:"
                    "[{text, match_type}]}]}.",
     "input_schema": {"type": "object",
                      "properties": {"account_id": {"type": "integer"},
                                     "spec": {"type": "object"}},
                      "required": ["account_id", "spec"]}},
]


def _run_tool(db: Session, client_ads, name: str, args: dict) -> str:
    def account():
        a = db.get(ClientAccount, int(args["account_id"]))
        if not a:
            raise ValueError(f"No account with id {args['account_id']}")
        return a

    if name == "list_accounts":
        return json.dumps([{
            "id": a.id, "name": a.name, "vertical": a.vertical,
            "mode": a.mode.value, "campaigns": len(a.campaigns),
            "pending_proposals": sum(
                1 for p in a.proposals if p.status == ProposalStatus.PENDING),
        } for a in db.query(ClientAccount).all()])

    if name == "get_account_data":
        a = account()
        return json.dumps([{
            "campaign_id": c.id, "name": c.name, "status": c.status,
            "daily_budget_readonly": c.daily_budget,
            "geo_target_type": c.geo_target_type,
            "bidding_strategy": c.bidding_strategy,
            "keywords": [{"id": k.id, "text": k.text, "match_type": k.match_type,
                          "status": k.status, "cpc_bid": k.cpc_bid,
                          "clicks": k.clicks, "cost": k.cost,
                          "conversions": k.conversions} for k in c.keywords],
            "search_terms": [{"term": t.term, "clicks": t.clicks, "cost": t.cost,
                              "conversions": t.conversions} for t in c.search_terms],
        } for c in a.campaigns])

    if name == "audit_account":
        return audit_markdown(db, account())

    if name == "sync_account":
        return json.dumps(sync_account(db, client_ads, account()))

    if name == "queue_change":
        a = account()
        if a.mode == Mode.AUTOMATIC:
            gateway = AdsGateway(client_ads, db)
            result = gateway.apply(a, args["change_type"], args["entity_ref"],
                                   args["payload"], actor="agent")
            return json.dumps({"applied": True, "result": result})
        db.add(ChangeProposal(account_id=a.id, rule="agent",
                              change_type=args["change_type"],
                              entity_ref=args["entity_ref"],
                              payload=args["payload"],
                              reasoning=args["reasoning"]))
        db.commit()
        return json.dumps({"queued_for_review": True})

    if name == "create_campaign":
        result = build_campaign(db, AdsGateway(client_ads, db), account(),
                                dict(args["spec"]), actor="agent")
        return json.dumps(result)

    raise ValueError(f"Unknown tool {name}")


class ChatIn(BaseModel):
    messages: list[dict]  # [{role, content}]


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db)):
    api_key = settings.anthropic_api_key
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    from .api import _ads_client  # share the in-memory mock state

    messages = [{"role": m["role"], "content": m["content"]}
                for m in body.messages][-30:]

    try:
        while True:
            response = client.messages.create(
                model=MODEL,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=SYSTEM,
                tools=TOOLS,
                messages=messages,
            )
            if response.stop_reason != "tool_use":
                break

            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                try:
                    out = _run_tool(db, _ads_client, block.name, dict(block.input))
                    results.append({"type": "tool_result",
                                    "tool_use_id": block.id, "content": out})
                except (BudgetChangeBlocked, PlaybookViolation, ValueError) as e:
                    results.append({"type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": f"Error: {e}", "is_error": True})
            messages.append({"role": "user", "content": results})
    except anthropic.AuthenticationError:
        raise HTTPException(503, "Agent unavailable: no valid Anthropic API key "
                                 "configured (set LOCALADS_ANTHROPIC_API_KEY).")
    except anthropic.APIConnectionError:
        raise HTTPException(503, "Agent unavailable: cannot reach the Anthropic API.")

    reply = "".join(b.text for b in response.content if b.type == "text")
    return {"reply": reply or "(no reply)"}
