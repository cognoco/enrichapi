# EnrichAPI

A pay-per-call Lead Enrichment API. Input a company URL, get back a structured B2B intelligence profile — industry, tech stack, ICP fit score, pain hypothesis, and a personalized outreach angle.

Built with FastAPI · Claude (claude-sonnet-4-6) · SQLite · Redis/fakeredis

---

## Quick Start

```bash
# 1. Install dependencies (uv recommended)
uv venv && source .venv/bin/activate && uv pip install -r requirements.txt
# or standard pip: pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — at minimum, set ANTHROPIC_API_KEY

# 3. Start the server
uvicorn main:app --reload
```

On first startup, a default dev API key is printed to the logs:

```
INFO  main — ============================================================
INFO  main — DEV API KEY (save this): <your-key-here>
INFO  main — ============================================================
```

Save that key — you'll need it for all requests.

---

## Interactive Docs

FastAPI auto-generates full API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Endpoints

### `POST /enrich`

Enrich a company profile.

**Headers:**
```
X-API-Key: <your-key>
Content-Type: application/json
```

**Request body:**
```json
{
  "url": "https://stripe.com",
  "icp": {
    "description": "B2B SaaS, 10-200 employees, US/EU",
    "ideal_roles": ["Head of Sales", "RevOps Manager"]
  },
  "offer_context": "AI automation tool for SDR workflows",
  "depth": "standard"
}
```

**Depth tiers:**

| `depth`    | Latency  | Fields returned                                      | Credits |
|------------|----------|------------------------------------------------------|---------|
| `quick`    | 1–3s     | Company basics only                                  | 1       |
| `standard` | 5–10s    | Full profile + ICP score + pain hypothesis + angle   | 1       |
| `deep`     | 10–20s   | Standard + funding/hiring signals + opening line     | 3       |

### `GET /health`

Liveness check. No auth required.

### `POST /keys/generate`

Generate a new API key. **Protect this endpoint in production.**

```json
{ "name": "my-app" }
```

### `GET /keys/usage`

Usage stats for the authenticated key (last 50 calls).

---

## Testing with cURL

```bash
# 1. Health check
curl http://localhost:8000/health

# 2. Set your key
export ENRICH_API_KEY="<your-key>"

# 3. Quick enrichment
curl -s -X POST http://localhost:8000/enrich \
  -H "X-API-Key: $ENRICH_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://linear.app", "depth": "quick"}' | jq

# 4. Standard enrichment with ICP
curl -s -X POST http://localhost:8000/enrich \
  -H "X-API-Key: $ENRICH_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://linear.app",
    "icp": {
      "description": "B2B SaaS, 10-200 employees",
      "ideal_roles": ["Head of Engineering", "CTO"]
    },
    "offer_context": "Developer productivity tool",
    "depth": "standard"
  }' | jq
```

Or run the included test script:

```bash
chmod +x test_enrich.sh
ENRICH_API_KEY="<your-key>" ./test_enrich.sh
```

---

## Configuration

All configuration via environment variables. See `.env.example` for full list.

| Variable                          | Required | Default                          | Description                         |
|-----------------------------------|----------|----------------------------------|-------------------------------------|
| `ANTHROPIC_API_KEY`               | **Yes**  | —                                | Claude API key                      |
| `STRIPE_ENABLED`                  | No       | `false`                          | Enable live Stripe billing          |
| `STRIPE_RESTRICTED_KEY_TWOFLOWER` | No       | —                                | Stripe restricted key               |
| `DATABASE_URL`                    | No       | `sqlite:///./enrichapi.db`       | SQLAlchemy connection string        |
| `REDIS_URL`                       | No       | `redis://localhost:6379`         | Redis URL (falls back to fakeredis) |
| `RATE_LIMIT_PER_DAY`              | No       | `100`                            | Max calls per API key per day       |

---

## Architecture

```
Request
  └─ FastAPI (main.py)
       ├─ Auth + rate limit   (APIKey in SQLite)
       ├─ Cache check         (Redis / fakeredis — 24h TTL per domain+depth)
       ├─ Web scrape          (httpx + BeautifulSoup)
       ├─ Claude enrichment   (claude-sonnet-4-6, streaming)
       ├─ Cache write
       └─ Usage log           (SQLite)
```

**Caching:** Same domain + depth combination is cached for 24 hours. Cached responses are free (not billed).

**Billing:** Currently in mock mode — logs charges but does not bill. Set `STRIPE_ENABLED=true` with a valid key to enable.

---

## Deploying to Render

1. Create a new Web Service on render.com
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables (at minimum `ANTHROPIC_API_KEY`)
5. For Redis: add a Redis instance and set `REDIS_URL`
6. For persistent DB: upgrade `DATABASE_URL` to a PostgreSQL connection string

---

## Roadmap

- [ ] Stripe live billing (Meter Events)
- [ ] x402/USDC payment endpoint for AI agent buyers
- [ ] Zapier / Make integration
- [ ] Batch enrichment endpoint (up to 100 URLs)
- [ ] Webhook callbacks for async deep enrichments
