import json
import logging
import os
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-sonnet-4-6"

SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; EnrichAPI/1.0; "
        "contact: hi@enrichapi.dev)"
    )
}


async def _scrape(url: str) -> str:
    """Fetch website and return cleaned text (max 8 000 chars)."""
    try:
        from bs4 import BeautifulSoup

        async with httpx.AsyncClient(
            timeout=12, follow_redirects=True, headers=SCRAPE_HEADERS
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        # Collapse whitespace
        import re
        text = re.sub(r"\s{2,}", " ", text)
        return text[:8000]

    except httpx.HTTPStatusError as e:
        logger.warning("HTTP %s fetching %s", e.response.status_code, url)
        return f"[Could not fetch website — HTTP {e.response.status_code}]"
    except Exception as e:
        logger.warning("Scrape error for %s: %s", url, e)
        return f"[Could not fetch website: {type(e).__name__}]"


def _build_prompt(
    url: str,
    content: str,
    depth: str,
    icp: Optional[dict],
    offer_context: Optional[str],
) -> str:
    domain = urlparse(url).netloc.lstrip("www.")

    icp_block = ""
    if icp:
        roles = ", ".join(icp.get("ideal_roles") or []) or "not specified"
        icp_block = f"""
ICP Context:
- Description: {icp.get("description") or "not provided"}
- Ideal Roles: {roles}
"""

    offer_block = f"\nOffer Context: {offer_context}" if offer_context else ""

    depth_guide = {
        "quick": (
            "Return ONLY the `company` object. "
            "Skip tech_stack, signals, icp_fit, pain_hypothesis, "
            "outreach_angle, and opening_line."
        ),
        "standard": (
            "Return company, tech_stack, icp_fit (if ICP provided), "
            "pain_hypothesis, and outreach_angle. "
            "Omit signals and opening_line."
        ),
        "deep": (
            "Return all fields: company, tech_stack, signals, icp_fit "
            "(if ICP provided), pain_hypothesis, outreach_angle, and opening_line. "
            "Be thorough on signals and make the opening_line feel genuinely human."
        ),
    }
    instruction = depth_guide.get(depth, depth_guide["standard"])

    no_icp_note = (
        "\nNo ICP was provided — omit icp_fit entirely."
        if not icp
        else ""
    )

    return f"""You are a senior B2B sales intelligence analyst. Analyze the company website below and produce a structured enrichment profile for an SDR or AE.

URL: {url}
Domain: {domain}
Depth: {depth}{icp_block}{offer_block}

Website content:
---
{content}
---

Instructions: {instruction}{no_icp_note}

Return ONLY a valid JSON object — no markdown, no explanation, no code fences.

Schema (include only the fields required for this depth):
{{
  "company": {{
    "name": "string",
    "domain": "{domain}",
    "description": "2-3 sentences: what they do and who they serve",
    "industry": "string",
    "size_estimate": "e.g. 50–150 employees",
    "stage": "e.g. Series A–B or bootstrapped",
    "business_model": "e.g. SaaS subscription",
    "founded_estimate": "e.g. ~2019",
    "hq": "City, State, Country"
  }},
  "tech_stack": {{
    "crm": "string or null",
    "hosting": "string or null",
    "analytics": "string or null",
    "payments": "string or null",
    "support": "string or null",
    "signals": ["list of other detectable tech signals"]
  }},
  "signals": {{
    "recent_funding": "string or null",
    "hiring": "string or null",
    "news": "string or null",
    "growth_signal": "string or null"
  }},
  "icp_fit": {{
    "score": 0-100,
    "reasoning": "string"
  }},
  "pain_hypothesis": "string — the specific pain this company likely has",
  "outreach_angle": "string — strategic angle for a cold outreach",
  "opening_line": "string — personalized, non-cringe cold email opener"
}}

If a field cannot be determined from the available content, use null. Do not fabricate specific facts (funding amounts, employee counts) unless clearly stated on the site — use estimates with qualifiers like "~" or "likely".
"""


async def enrich(
    url: str,
    depth: str = "standard",
    icp: Optional[dict] = None,
    offer_context: Optional[str] = None,
) -> dict:
    """Scrape the URL and generate enrichment via Claude. Returns raw dict."""
    from anthropic import AsyncAnthropic

    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    content = await _scrape(url)
    prompt = _build_prompt(url, content, depth, icp, offer_context)

    max_tokens = {"quick": 800, "standard": 2000, "deep": 3200}.get(depth, 2000)

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    # Use streaming to avoid timeouts on longer generations
    full_text = ""
    async with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for chunk in stream.text_stream:
            full_text += chunk

    raw = full_text.strip()

    # Strip accidental markdown code fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first and last fence lines
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error. Raw response (first 500): %s", raw[:500])
        raise ValueError(f"Claude returned invalid JSON: {exc}") from exc
