"""Generate the LocalAds Manager design document PDF.

This document is formatted for submission with a Google Ads API
developer token application (Basic Access). Regenerate after edits:

    python3 docs/generate_design_doc.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).parent / "LocalAds-Manager-Design-Document.pdf"

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, spaceAfter=10,
                    textColor=colors.HexColor("#1a2e4a"))
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12.5, spaceBefore=14,
                    spaceAfter=6, textColor=colors.HexColor("#1a2e4a"))
BODY = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=14,
                      spaceAfter=6)
BULLET = ParagraphStyle("Bullet", parent=BODY, leftIndent=18, bulletIndent=6)
TITLE = ParagraphStyle("DocTitle", parent=styles["Title"], fontSize=22,
                       textColor=colors.HexColor("#1a2e4a"), spaceAfter=4)
SUB = ParagraphStyle("Sub", parent=BODY, fontSize=10.5,
                     textColor=colors.HexColor("#555555"))


def p(text, style=BODY):
    return Paragraph(text, style)


def bullets(items):
    return [Paragraph(f"• {t}", BULLET) for t in items]


def table(data, widths):
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2e4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f2f5f9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def cell(text):
    return Paragraph(text, ParagraphStyle("cell", parent=BODY, fontSize=9,
                                          leading=12, spaceAfter=0))


flow = [
    p("LocalAds Manager", TITLE),
    p("Design Documentation — Google Ads API Developer Token Application", SUB),
    p("Document version 1.0 · June 2026", SUB),
    Spacer(1, 6),
    HRFlowable(width="100%", color=colors.HexColor("#1a2e4a"), thickness=1.5),
    Spacer(1, 10),

    p("1. Overview", H1),
    p("LocalAds Manager is an <b>internal campaign-management tool</b> used by our "
      "agency to plan, create, monitor, and optimize Google Ads Search campaigns for "
      "the local-business clients whose advertising we manage. The tool is operated "
      "exclusively by our own staff under our Manager (MCC) account. It is <b>not</b> "
      "licensed, sold, or made available to any third party, and no third party "
      "interacts with the Google Ads API through it."),
    p("The tool exists to apply a consistent, conservative optimization methodology "
      "for local service businesses (tight match types, precise geographic targeting, "
      "structured negative keyword management) and to give our account managers a "
      "review-and-approve workflow so that every material change to a client account "
      "is deliberate, logged, and auditable."),

    p("2. Users and Access Model", H1),
    *bullets([
        "<b>Users:</b> internal agency staff only (account managers). Each user "
        "authenticates to the tool itself; the tool authenticates to the Google Ads "
        "API via OAuth 2.0 credentials tied to our Manager account.",
        "<b>Accounts accessed:</b> only client accounts linked under our MCC, with "
        "standard Google Ads account-linking consent.",
        "<b>No third-party access:</b> the tool is internal-use software. It is not "
        "offered as a SaaS product and has no external sign-up.",
    ]),

    p("3. System Architecture", H1),
    p("The system has four components:"),
    *bullets([
        "<b>Web dashboard</b> — internal web application where staff view account "
        "performance, review and approve proposed changes, create campaigns, and "
        "export reports/audits.",
        "<b>Strategy engine</b> — a deterministic rules layer that evaluates "
        "account performance against our local-business playbook and produces "
        "<i>change proposals</i> with written reasoning (e.g., add a negative keyword, "
        "adjust a keyword bid, pause an underperforming ad).",
        "<b>Scheduler / sync service</b> — fetches reporting data on a fixed "
        "schedule (1–2 times per day per account) and caches it locally so the "
        "dashboard does not generate per-pageview API traffic.",
        "<b>Google Ads API integration layer</b> — a single gateway module through "
        "which all API calls pass. It enforces guardrails (Section 6), batching, "
        "retry/backoff, and full audit logging of every mutate operation.",
    ]),
    p("Change proposals flow through a human review queue by default (“review "
      "mode”). An account may be switched to “automatic mode,” in which "
      "pre-approved, low-risk change types are applied without per-change sign-off; "
      "all changes remain logged and visible in the dashboard either way."),

    p("4. Google Ads API Services Used", H1),
    table(
        [["API Service", "Operations", "Purpose"],
         [cell("GoogleAdsService (SearchStream)"), cell("Read"),
          cell("Scheduled retrieval of campaign, ad group, keyword, search-term, and "
               "geographic performance reports.")],
         [cell("CampaignService"), cell("Read / Mutate"),
          cell("Create Search campaigns; update campaign settings (network settings, "
               "status). Budget fields are never mutated — see Section 6.")],
         [cell("CampaignBudgetService"), cell("Create only"),
          cell("Create a budget once at campaign creation, at the amount entered by "
               "the account manager. The tool contains no code path that updates an "
               "existing budget.")],
         [cell("AdGroupService"), cell("Read / Mutate"),
          cell("Create and organize ad groups; pause/enable.")],
         [cell("AdGroupAdService"), cell("Read / Mutate"),
          cell("Create responsive search ads; pause underperforming ads after human "
               "review.")],
         [cell("AdGroupCriterionService"), cell("Read / Mutate"),
          cell("Add/edit keywords (phrase and exact match), set keyword-level bids, "
               "add ad-group negatives.")],
         [cell("CampaignCriterionService"), cell("Read / Mutate"),
          cell("Location targeting (radius/geo, “presence” setting), campaign "
               "negative keywords, ad schedules.")],
         [cell("SharedSetService / SharedCriterionService"), cell("Read / Mutate"),
          cell("Maintain shared negative keyword lists per client vertical.")],
         [cell("AssetService / CampaignAssetService"), cell("Read / Mutate"),
          cell("Call, sitelink, callout, and location assets.")],
         [cell("RecommendationService"), cell("Read / Dismiss"),
          cell("Recommendations are surfaced to staff for information only; the tool "
               "never auto-applies recommendations.")],
        ],
        [1.9 * inch, 1.0 * inch, 3.6 * inch],
    ),

    p("5. API Usage Patterns and Volume", H1),
    *bullets([
        "Reporting syncs run on a schedule (typically twice daily per client account) "
        "using GoogleAdsService.SearchStream, with results cached in our database. "
        "Dashboard page views are served from the cache, not live API calls.",
        "Mutate operations are batched per service and submitted only when a human "
        "approves a proposal (review mode) or when a pre-approved rule fires "
        "(automatic mode). Expected volume is low — tens of mutate operations per "
        "account per week.",
        "The integration layer implements exponential backoff with jitter on "
        "RESOURCE_EXHAUSTED / transient errors and respects all documented rate "
        "limits and daily operation quotas.",
        "Initial usage: fewer than 50 client accounts under one MCC. Basic Access "
        "quota is sufficient.",
    ]),

    p("6. Guardrails and Change Safety", H1),
    *bullets([
        "<b>Budget immutability:</b> the integration layer hard-blocks any mutate "
        "touching CampaignBudget amounts after creation. Budget changes are made only "
        "by a human directly in the Google Ads interface.",
        "<b>Cooldown windows:</b> the strategy engine will not modify the same "
        "entity more than once within a configured cooldown period, and bid "
        "adjustments are capped per change, preventing oscillating or aggressive "
        "automation.",
        "<b>Statistical thresholds:</b> keywords/ads are only proposed for pausing "
        "after sufficient data volume, never on small samples.",
        "<b>Full audit trail:</b> every API mutate is recorded with timestamp, "
        "operator (or rule), before/after values, and reasoning; auditable and "
        "exportable from the dashboard.",
    ]),

    p("7. Data Storage, Privacy, and Security", H1),
    *bullets([
        "The tool stores campaign structure and aggregate performance metrics "
        "(impressions, clicks, conversions, cost) per client account. It does not "
        "collect or store end-user data or personally identifiable information.",
        "OAuth 2.0 refresh tokens and the developer token are stored encrypted in "
        "environment-level secrets, never in source control or client-side code.",
        "Performance data for one client account is never shared with, or used to "
        "make decisions for, any other client account.",
        "Access to the dashboard is restricted to authenticated agency staff over "
        "HTTPS.",
    ]),

    p("8. Compliance", H1),
    *bullets([
        "The tool is internal-use software operated by the advertiser’s "
        "authorized agency; it is not distributed to third parties, so third-party "
        "Required Minimum Functionality obligations do not apply. It nonetheless "
        "supports full campaign creation, management, and reporting workflows.",
        "The tool complies with the Google Ads API Terms and Conditions and the "
        "Google Ads API policies, including data-use and attribution requirements.",
        "No scraping, no automated account creation, no circumvention of Google Ads "
        "policies. All advertising content is created or approved by account "
        "managers.",
    ]),

    p("9. Dashboard Screens (Summary)", H1),
    *bullets([
        "<b>Accounts overview</b> — all linked client accounts with mode "
        "(review/automatic), spend pace, and key metrics.",
        "<b>Account detail</b> — campaigns, ad groups, keywords, and search terms "
        "with cached performance data.",
        "<b>Proposal queue</b> — pending changes with reasoning; approve, edit, or "
        "reject. Approval triggers the corresponding batched mutate.",
        "<b>Campaign builder</b> — guided Search-campaign creation enforcing our "
        "local-business standards (match types, geo settings, negatives, assets).",
        "<b>Reports & audits</b> — exportable performance reports and account "
        "audits (CSV/PDF) for client communication.",
    ]),
]

doc = SimpleDocTemplate(str(OUT), pagesize=LETTER,
                        leftMargin=0.85 * inch, rightMargin=0.85 * inch,
                        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
                        title="LocalAds Manager — Design Documentation",
                        author="LocalAds Manager")
doc.build(flow)
print(f"Wrote {OUT}")
