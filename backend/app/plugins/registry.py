"""Built-in tool plugins plus declared capabilities that are not implemented yet.

A declared-only tool is registered with ``available=False`` so agents and the UI can see it
exists as a requirement, but nothing can call it.
"""

from app.core.domain import CostTier, Permission, RiskLevel
from app.plugins import business_discovery, web_fetch, website_auditor
from app.plugins.base import ToolDefinition


def _declared(
    slug: str, name: str, description: str, permission: Permission, risk: RiskLevel
) -> ToolDefinition:
    return ToolDefinition(
        slug=slug, name=name, description=description, provider="not connected",
        cost_tier=CostTier.FREE, permission=permission, risk_level=risk,
        input_schema={}, output_schema={},
    )  # fmt: skip


LLM_TOOL = ToolDefinition(
    slug="llm",
    name="AI Model Router",
    description="Routes a prompt to the cheapest capable configured model (local → free tier → "
    "low-cost → premium with budget limits).",
    provider="matt",
    cost_tier=CostTier.FREE,
    permission=Permission.READ,
    risk_level=RiskLevel.LOW,
    input_schema={"type": "object", "properties": {"prompt": {"type": "string"}}},
    output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
)

DATABASE_TOOL = ToolDefinition(
    slug="database",
    name="MATT Database",
    description="Reads and writes MATT's own records (businesses, leads, knowledge).",
    provider="matt",
    cost_tier=CostTier.FREE,
    permission=Permission.WRITE,
    risk_level=RiskLevel.LOW,
    input_schema={},
    output_schema={},
)

TOOLS: list[ToolDefinition] = [
    LLM_TOOL,
    DATABASE_TOOL,
    web_fetch.TOOL,
    website_auditor.TOOL,
    business_discovery.TOOL,
    _declared(
        "web_search",
        "Web Search",
        "Search engine queries. Needs a search API key.",
        Permission.READ,
        RiskLevel.LOW,
    ),
    _declared(
        "email",
        "Email",
        "Sending email. Needs an email provider; every send is approval-gated.",
        Permission.EXTERNAL_ACTION,
        RiskLevel.HIGH,
    ),
    _declared(
        "crm",
        "CRM",
        "External CRM sync. MATT's built-in leads table is used meanwhile.",
        Permission.WRITE,
        RiskLevel.MEDIUM,
    ),
    _declared(
        "browser",
        "Browser Automation",
        "Headless browsing for pages that need JavaScript.",
        Permission.READ,
        RiskLevel.MEDIUM,
    ),
    _declared(
        "code_execution",
        "Sandboxed Code Execution",
        "Runs code in an isolated sandbox.",
        Permission.ADMIN,
        RiskLevel.HIGH,
    ),
    _declared("git", "Git", "Repository operations.", Permission.WRITE, RiskLevel.MEDIUM),
    _declared(
        "github", "GitHub", "Pull requests and issues.", Permission.EXTERNAL_ACTION, RiskLevel.HIGH
    ),
    _declared(
        "image_generation", "Image Generation", "Generates images.", Permission.READ, RiskLevel.LOW
    ),
    _declared(
        "video_generation",
        "Video Generation",
        "Edits and renders rights-cleared video.",
        Permission.READ,
        RiskLevel.LOW,
    ),
    _declared(
        "speech_to_text", "Speech to Text", "Transcribes audio.", Permission.READ, RiskLevel.LOW
    ),
    _declared(
        "text_to_speech", "Text to Speech", "Speaks responses.", Permission.READ, RiskLevel.LOW
    ),
    _declared(
        "analytics", "Analytics", "External analytics sources.", Permission.READ, RiskLevel.LOW
    ),
    _declared(
        "calendar", "Calendar", "Scheduling meetings.", Permission.EXTERNAL_ACTION, RiskLevel.MEDIUM
    ),
]

IMPLEMENTED = {"llm", "database", "web_fetch", "website_auditor", "business_discovery"}
BY_SLUG = {t.slug: t for t in TOOLS}
