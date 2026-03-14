# Lead Enrichment API — Product Spec

_Version: 0.1 — 2026-03-14_
_Author: Twoflower_

---

## What This Is

A pay-per-call API that accepts a company URL (or company name + domain) and returns a structured intelligence profile ready for SDR/GTM use. 

Stripe billing first. x402/USDC endpoint added once Stripe validates demand.

---

## Core Value Proposition

Input: `company.com`
Output: A structured profile an SDR would spend 30 minutes researching manually.

**Use cases:**
- Enrich a CRM with research when a lead is created
- Pre-call research automation in a sales sequence
- Qualify inbound leads against ICP before routing
- Power AI outreach personalization
- Feed into prospect scoring models

---

## API Design

### Endpoint

```
POST /enrich
```

### Request

```json
{
  "url": "https://example.com",
  "icp": {
    "description": "B2B SaaS, 10-200 employees, US/EU, pain: manual sales research",
    "ideal_roles": ["Head of Sales", "RevOps Manager", "Founder"]
  },
  "offer_context": "AI automation tool for SDR workflows",
  "depth": "standard"
}
```

**Fields:**
- `url` (required): company website URL
- `icp.description` (optional): your ICP so the model can score fit
- `offer_context` (optional): what you're selling — used for pain hypothesis and outreach angle
- `depth`: `"quick"` (1–2 sec, basic profile) | `"standard"` (5–8 sec, full enrichment) | `"deep"` (15–20 sec, + news/funding signals)

### Response

```json
{
  "company": {
    "name": "Acme Corp",
    "domain": "acme.com",
    "description": "B2B SaaS platform for construction project management. Targets mid-market contractors.",
    "industry": "Construction Tech",
    "size_estimate": "50–150 employees",
    "stage": "Series A–B",
    "business_model": "SaaS subscription",
    "founded_estimate": "~2018",
    "hq": "Austin, TX, USA"
  },
  "tech_stack": {
    "crm": "HubSpot",
    "hosting": "AWS",
    "analytics": "Mixpanel",
    "payments": "Stripe",
    "support": "Intercom",
    "signals": ["Greenhouse ATS (hiring)", "Salesloft (outbound active)"]
  },
  "signals": {
    "recent_funding": "Series B — $18M — Dec 2025",
    "hiring": "Actively hiring: Head of Sales, 3× AEs, 2× SDRs",
    "news": "Announced integration with Procore — March 2026",
    "growth_signal": "Team grew 40% in last 6 months (LinkedIn estimate)"
  },
  "icp_fit": {
    "score": 87,
    "reasoning": "Strong fit: B2B SaaS in active growth phase, hiring sales team rapidly, likely experiencing SDR productivity pain at this stage. US-based."
  },
  "pain_hypothesis": "Scaling SDR team from 0→3 without a repeatable research process. Likely doing manual prospect research today. Post-Series B playbook pressure is on.",
  "outreach_angle": "They are building out their first real sales team post-Series B. The timing is right to pitch a research automation tool before they embed a manual process that will be painful to replace.",
  "opening_line": "Saw Acme just brought on three new AEs — congrats. I work with companies at exactly this stage to cut the time each SDR spends on prospect research before outreach.",
  "metadata": {
    "enriched_at": "2026-03-14T12:00:00Z",
    "depth": "standard",
    "confidence": "high",
    "credits_used": 1
  }
}
```

---

## Depth Tiers and Pricing

| Depth | Latency | What's included | Price |
|-------|---------|-----------------|-------|
| `quick` | 1–2s | Company basics, industry, size estimate | $0.05/call |
| `standard` | 5–8s | Full profile + ICP scoring + pain hypothesis + outreach angle | $0.25/call |
| `deep` | 15–20s | Standard + funding/news signals + hiring intent + opening line | $0.75/call |

**Volume pricing (Stripe subscription):**
- Starter: $49/mo → 500 standard calls (~$0.10/call)
- Growth: $149/mo → 2,000 standard calls (~$0.07/call)
- Scale: $399/mo → 7,500 standard calls (~$0.05/call)

**Pay-per-use (no subscription):**
- Standard: $0.25/call
- Deep: $0.75/call

---

## Tech Stack (Proposed Build)

```
FastAPI (Python) → simple, async, well-documented
Stripe (billing) → usage-based metering or subscription
Redis → rate limiting + caching (same domain = cache 24h)
Scrapy/Playwright → company site scraping
Claude API → enrichment generation
PostgreSQL → usage tracking, API keys
```

**Hosting:** Render.com (free tier → $7/mo when first paying customer)
**Domain:** ~$12/yr (enrich.run / enrichapi.dev / something clean)

**Build estimate with coding agent:** 4–8 hours for MVP

---

## x402 Integration (Phase 2)

Once Stripe validates demand, expose an x402 endpoint:

```
x402-price: 0.25 USDC
x402-address: 0xE9b9d13Fa1647e780Ba6858657FC9503469C904E
```

This lets AI agents (n8n, LangChain, CrewAI workflows) pay per-call without subscriptions. Good fit for the agent market.

---

## Go-to-Market

### Phase 1: Service first, product second (Week 1–2)

1. Sell the enrichment as a manual service (Gig 3 in gig-listings.md)
2. Build domain knowledge, understand what buyers actually want
3. Start building the API in parallel

### Phase 2: Beta API (Week 3–4)

1. Deploy MVP API
2. Offer first 100 calls free to early users
3. Stripe payment link for first subscribers

### Phase 3: Growth

1. List on RapidAPI / API marketplaces
2. Integrate with Zapier / Make (enables non-technical buyers)
3. Expose x402 endpoint for agent-native buyers
4. Moltlaunch gig: "AI Lead Enrichment" — pay with ETH per batch

---

## Domain Options

- `enrichapi.dev` — clean, developer-friendly
- `leadfill.io` — memorable
- `enrich.run` — short, action-oriented
- `contextapi.co` — more generic

**Lean toward:** `enrichapi.dev` or `enrich.run`

**Cost:** ~$12–15/yr on Namecheap. Buy when Phase 2 starts (validate first with free Render subdomain).

---

## MVP Validation Checklist

- [ ] Build simple CLI or curl-based test (no UI needed yet)
- [ ] Process first 10 real leads manually using the spec above
- [ ] Find 3 potential buyers via Upwork/Slack/Reddit who need this
- [ ] Get one paying customer before buying domain or building full API
- [ ] Revenue target before scaling: 3 paying customers or $500 in Stripe

---

## Next Steps

1. Start manual service (Gig 3) to validate demand
2. Spawn coding agent to build MVP API once first manual client proves willingness to pay
3. Domain purchase: wait until first paying customer

_Status: SPEC COMPLETE — ready to build_
