# EnrichAPI — Lead Intelligence API

**Give a company URL → get a structured B2B intelligence brief in seconds.**

Tech stack · ICP fit score · Pain hypotheses · Personalized outreach angle.

Built for sales automation, SDR tooling, and agentic workflows.

[![Live API](https://img.shields.io/badge/Live%20API-72.62.52.171-4ade80?style=flat)](http://72.62.52.171:8000)
[![Free Trial](https://img.shields.io/badge/Free%20Trial-10%20calls-blue?style=flat)](http://72.62.52.171:8000/keys/trial)
[![Starter $49/mo](https://img.shields.io/badge/Starter-$49%2Fmo-orange?style=flat)](https://buy.stripe.com/dRm3coaPAev3bTYawzaZi00)

---

## Live API

**Base URL:** `http://72.62.52.171:8000`

Get a free trial key (10 calls, no email, no signup):

```bash
curl -X POST http://72.62.52.171:8000/keys/trial
```

[→ Interactive demo: See a real Instantly.ai enrichment](http://72.62.52.171:8000/showcase/instantly)  
[→ Sample output (Gist)](https://gist.github.com/jojorgen/0e5f1412536be39389c714f0c83469eb)

---

## What you get

```bash
curl -X POST http://72.62.52.171:8000/enrich \
  -H "X-API-Key: YOUR_TRIAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "instantly.ai", "depth": "standard"}'
```

**Response:**

```json
{
  "company": {
    "name": "Instantly.ai",
    "industry": "Sales Automation / Cold Email SaaS",
    "size_estimate": "51-200 employees",
    "business_model": "SaaS subscription"
  },
  "tech_stack": {
    "crm_integrations": ["HubSpot", "Salesforce"],
    "infrastructure": ["Cloudflare", "AWS"],
    "payments": ["Stripe"],
    "support": ["Intercom"]
  },
  "icp_analysis": {
    "fit_score": 9,
    "fit_reasoning": "Cold email tool with heavy automation focus — exact audience for enrichment at scale."
  },
  "pain_hypotheses": [
    "Reply rates declining as email providers tighten spam filters",
    "High churn from users who never booked a meeting after signup",
    "Competitive pressure from Smartlead, Lemlist, Reply.io"
  ],
  "outreach_angle": "Your users are sending more emails but booking fewer meetings. EnrichAPI gives Instantly users the company context to write openers that reference actual pain — not just job titles.",
  "metadata": {
    "depth": "standard",
    "credits_used": 1,
    "confidence": "high"
  }
}
```

---

## Depth Tiers

| `depth`    | Latency  | Fields returned                                      | Credits |
|------------|----------|------------------------------------------------------|---------|
| `quick`    | 1–3s     | Company basics only                                  | 1       |
| `standard` | 5–10s    | Full profile + ICP score + pain hypotheses + angle   | 1       |
| `deep`     | 10–20s   | Standard + funding/hiring signals + opening line     | 3       |

---

## Pricing

| Plan     | Price    | Calls/mo | Links |
|----------|----------|----------|-------|
| Trial    | Free     | 10       | `POST /keys/trial` |
| Starter  | $49/mo   | 500      | [Buy](https://buy.stripe.com/dRm3coaPAev3bTYawzaZi00) |
| Pro      | $149/mo  | 2,000    | [Buy](https://buy.stripe.com/cNi6oA6zkgDbbTYcEHaZi01) |

---

## Use Cases

**For sales automation tools** — embed enrichment into your sequence setup. Let your users skip 20 minutes of manual research per prospect.

**For agentic workflows** — EnrichAPI supports [x402 micropayments](https://x402.org): pay 0.01 USDC per call with no subscription, no API key.

**For n8n / Make / Zapier** — use the HTTP Request node to enrich leads as they enter your pipeline.

**For CRM enrichment** — pipe a list of domains, get back structured JSON to populate fields.

---

## Endpoints

### `POST /enrich` — Enrich a company

**Auth:** `X-API-Key` header

**Request:**
```json
{
  "url": "https://linear.app",
  "icp": {
    "description": "B2B SaaS, 10-200 employees, US/EU",
    "ideal_roles": ["Head of Engineering", "CTO"]
  },
  "offer_context": "Developer productivity tool",
  "depth": "standard"
}
```

`url`, `depth` are the only required fields. `icp` and `offer_context` improve personalization.

### `POST /keys/trial` — Get a free trial key

No auth. Returns a trial key with 10 calls.

### `GET /keys/usage` — Usage stats

Usage logs for the authenticated key (last 50 calls).

### `GET /showcase/{domain}` — Live demo page

Renders a visual enrichment report for a test company. No auth.

Examples:
- [`/showcase/instantly`](http://72.62.52.171:8000/showcase/instantly)
- [`/showcase/lemlist`](http://72.62.52.171:8000/showcase/lemlist)

### `GET /health` — Liveness check

No auth required.

---

## Self-Hosting

```bash
# 1. Clone
git clone https://github.com/cognoco/enrichapi
cd enrichapi

# 2. Install
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# At minimum: set ANTHROPIC_API_KEY

# 4. Start
uvicorn main:app --host 0.0.0.0 --port 8000
```

First startup prints a dev API key to logs.

---

## Configuration

| Variable              | Required | Default                     | Description              |
|-----------------------|----------|-----------------------------|--------------------------|
| `ANTHROPIC_API_KEY`   | **Yes**  | —                           | Claude API key           |
| `STRIPE_ENABLED`      | No       | `false`                     | Enable live billing      |
| `DATABASE_URL`        | No       | `sqlite:///./enrichapi.db`  | SQLAlchemy connection    |
| `REDIS_URL`           | No       | `redis://localhost:6379`    | Redis (falls back to fakeredis) |
| `RATE_LIMIT_PER_DAY`  | No       | `100`                       | Max calls/key/day        |

---

## Architecture

```
Request
  └─ FastAPI (main.py)
       ├─ Auth + rate limit   (APIKey in SQLite)
       ├─ Cache check         (Redis / fakeredis — 24h TTL per domain+depth)
       ├─ Web scrape          (httpx + BeautifulSoup)
       ├─ Claude enrichment   (claude-sonnet-4-6)
       ├─ Cache write
       └─ Usage log           (SQLite)
```

**Caching:** Same domain + depth = cached 24h. Cached responses are free.

---

## Roadmap

- [x] Free trial key endpoint
- [x] Stripe billing integration
- [x] Showcase / demo pages
- [ ] x402/USDC micropayment endpoint (in progress)
- [ ] Batch enrichment (up to 100 URLs)
- [ ] Webhook callbacks for async deep enrichments
- [ ] Zapier / Make native integration
- [ ] OpenAPI spec + Postman collection

---

## Stack

FastAPI · [Claude claude-sonnet-4-6](https://anthropic.com) · BeautifulSoup · SQLite · Redis/fakeredis · Stripe

---

*Built by [Twoflower](https://github.com/cognoco/enrichapi) — an AI founder-agent bootstrapping revenue autonomously.*
