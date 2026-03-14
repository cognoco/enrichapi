import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Optional
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from billing import create_stripe_customer, report_usage
from cache import get_cached, set_cached
from database import APIKey, SessionLocal, UsageLog, get_db, init_db
from enrichment import enrich
from models import (
    EnrichRequest,
    GenerateKeyRequest,
    GenerateKeyResponse,
    UsageResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

RATE_LIMIT_PER_DAY = int(os.getenv("RATE_LIMIT_PER_DAY", "100"))

CREDITS_MAP = {"quick": 1, "standard": 1, "deep": 3}

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _ensure_dev_key()
    yield


def _ensure_dev_key():
    """Create a default API key on first run if none exist."""
    db = SessionLocal()
    try:
        if not db.query(APIKey).first():
            dev_key = secrets.token_urlsafe(32)
            db.add(APIKey(key=dev_key, name="dev-default"))
            db.commit()
            logger.info("=" * 60)
            logger.info("DEV API KEY (save this): %s", dev_key)
            logger.info("=" * 60)
    finally:
        db.close()


app = FastAPI(
    title="EnrichAPI",
    description=(
        "Lead Enrichment API — give us a company URL, "
        "get back a structured intelligence profile ready for SDR/GTM use."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth + rate-limit dependency
# ---------------------------------------------------------------------------


def require_api_key(
    api_key: str = Security(API_KEY_HEADER),
    db: Session = Depends(get_db),
) -> APIKey:
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Add header: X-API-Key: <your-key>",
        )

    record = (
        db.query(APIKey)
        .filter(APIKey.key == api_key, APIKey.is_active == True)  # noqa: E712
        .first()
    )
    if not record:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key.")

    # Reset daily counter at midnight UTC
    today = date.today()
    if record.last_reset.date() < today:
        record.calls_today = 0
        record.last_reset = datetime.utcnow()
        db.commit()

    if record.calls_today >= RATE_LIMIT_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit reached: {RATE_LIMIT_PER_DAY} calls/day. "
                "Upgrade your plan or wait until midnight UTC."
            ),
        )

    return record


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["System"])
def health():
    """Service liveness check."""
    return {"status": "ok", "version": "0.1.0", "service": "EnrichAPI"}


@app.post("/enrich", tags=["Enrichment"])
async def enrich_endpoint(
    request: EnrichRequest,
    key_record: APIKey = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    """
    Enrich a company profile from a URL.

    - **url**: Company website (required)
    - **icp**: Your ideal customer profile context (optional)
    - **offer_context**: What you're selling — improves pain hypothesis (optional)
    - **depth**: `quick` | `standard` | `deep` (default: `standard`)
    """
    # Normalise URL
    url = request.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    if not parsed.netloc:
        raise HTTPException(status_code=422, detail="Invalid URL provided.")

    domain = parsed.netloc.lower().removeprefix("www.")
    depth = request.depth if request.depth in CREDITS_MAP else "standard"
    credits = CREDITS_MAP[depth]

    # ── Cache check ──────────────────────────────────────────────────────────
    cached_result = get_cached(domain, depth)
    if cached_result:
        logger.info("Cache HIT %s [%s]", domain, depth)
        _log_usage(db, key_record, domain, depth, credits, cached=True)
        report_usage(key_record.key, depth, cached=True, stripe_customer_id=key_record.stripe_customer_id)
        return cached_result

    # ── Enrich via Claude ─────────────────────────────────────────────────────
    logger.info("Enriching %s [%s]", domain, depth)
    icp_dict = request.icp.dict() if request.icp else None

    try:
        result = await enrich(
            url=url,
            depth=depth,
            icp=icp_dict,
            offer_context=request.offer_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Enrichment failed for %s", url)
        raise HTTPException(status_code=502, detail=f"Enrichment error: {exc}")

    # Inject metadata
    result["metadata"] = {
        "enriched_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "depth": depth,
        "confidence": "high",
        "credits_used": credits,
    }

    # ── Cache + billing ───────────────────────────────────────────────────────
    set_cached(domain, depth, result)
    _log_usage(db, key_record, domain, depth, credits, cached=False)
    report_usage(key_record.key, depth, cached=False, stripe_customer_id=key_record.stripe_customer_id)

    return result


@app.post("/keys/generate", response_model=GenerateKeyResponse, tags=["API Keys"])
def generate_key(
    body: GenerateKeyRequest = GenerateKeyRequest(),
    db: Session = Depends(get_db),
):
    """
    Generate a new API key.

    ⚠️  In production, protect this endpoint with an admin secret or remove it.
    """
    new_key = secrets.token_urlsafe(32)
    record = APIKey(key=new_key, name=body.name or "unnamed")
    db.add(record)
    db.commit()
    db.refresh(record)

    # Create Stripe customer and persist the mapping
    stripe_customer_id = create_stripe_customer(new_key, name=record.name)
    if stripe_customer_id:
        record.stripe_customer_id = stripe_customer_id
        db.commit()

    return GenerateKeyResponse(
        api_key=new_key,
        name=record.name,
        created_at=record.created_at.isoformat(),
    )


@app.get("/keys/usage", tags=["API Keys"])
def key_usage(
    key_record: APIKey = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    """Return usage stats for the authenticated API key."""
    logs = (
        db.query(UsageLog)
        .filter(UsageLog.api_key == key_record.key)
        .order_by(UsageLog.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "api_key_prefix": key_record.key[:8] + "...",
        "name": key_record.name,
        "calls_today": key_record.calls_today,
        "rate_limit_per_day": RATE_LIMIT_PER_DAY,
        "recent_calls": [
            {
                "domain": log.domain,
                "depth": log.depth,
                "credits_used": log.credits_used,
                "cached": log.cached,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log_usage(
    db: Session,
    key_record: APIKey,
    domain: str,
    depth: str,
    credits: int,
    cached: bool,
) -> None:
    log = UsageLog(
        api_key=key_record.key,
        domain=domain,
        depth=depth,
        credits_used=credits,
        cached=cached,
    )
    db.add(log)
    key_record.calls_today += 1
    db.commit()


# ---------------------------------------------------------------------------
# Landing page + success page
# ---------------------------------------------------------------------------

from fastapi.responses import HTMLResponse


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing_page():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>EnrichAPI — Turn a URL into SDR-ready intelligence</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background: #0a0a0a; color: #e8e8e8; line-height: 1.6; }
.container { max-width: 860px; margin: 0 auto; padding: 0 24px; }
header { padding: 40px 0 20px; }
.badge { display: inline-block; background: #1a2a1a; color: #4ade80; border: 1px solid #2d5a2d; padding: 4px 12px; border-radius: 20px; font-size: 13px; margin-bottom: 20px; }
h1 { font-size: clamp(2rem, 5vw, 3.2rem); font-weight: 700; color: #fff; line-height: 1.2; margin-bottom: 16px; }
.sub { font-size: 1.15rem; color: #a0a0a0; max-width: 600px; margin-bottom: 32px; }
.cta-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 60px; }
.btn-primary { background: #4ade80; color: #0a0a0a; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px; }
.btn-secondary { background: transparent; color: #e8e8e8; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 500; font-size: 15px; border: 1px solid #333; }
.code-block { background: #111; border: 1px solid #222; border-radius: 10px; padding: 20px; font-family: 'Courier New',monospace; font-size: 13px; color: #a0ffb0; margin-bottom: 48px; overflow-x: auto; }
.features { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; margin-bottom: 60px; }
.feature { background: #111; border: 1px solid #1e1e1e; border-radius: 10px; padding: 20px; }
.feature h3 { color: #fff; margin-bottom: 8px; font-size: 15px; }
.feature p { color: #888; font-size: 14px; }
.pricing { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 60px; }
.plan { background: #111; border: 1px solid #1e1e1e; border-radius: 10px; padding: 24px; text-align: center; }
.plan.featured { border-color: #4ade80; }
.plan .price { font-size: 2rem; font-weight: 700; color: #fff; }
.plan .period { color: #666; font-size: 13px; }
.plan .credits { color: #888; margin: 8px 0 16px; font-size: 14px; }
.plan a { display: block; background: #4ade80; color: #0a0a0a; padding: 10px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 14px; }
.plan.secondary a { background: #1e1e1e; color: #e8e8e8; }
h2 { font-size: 1.6rem; color: #fff; margin-bottom: 24px; }
footer { border-top: 1px solid #1e1e1e; padding: 24px 0; color: #555; font-size: 13px; text-align: center; }
</style>
</head>
<body>
<div class="container">
<header>
  <div class="badge">🟢 API Live</div>
  <h1>Turn a company URL into<br>SDR-ready intelligence</h1>
  <p class="sub">POST one URL. Get back company profile, tech stack, funding signals, ICP fit score, pain hypothesis, and a personalized outreach angle. In under 8 seconds.</p>
  <div class="cta-row">
    <a href="https://buy.stripe.com/dRm3coaPAev3bTYawzaZi00" class="btn-primary">Start free — 100 calls included</a>
    <a href="/docs" class="btn-secondary">API Docs →</a>
  </div>
</header>

<div class="code-block">
<div style="color:#666;margin-bottom:12px"># Try it now</div>
curl -X POST https://enrichapi.app/enrich \\<br>
&nbsp;&nbsp;-H "X-API-Key: YOUR_KEY" \\<br>
&nbsp;&nbsp;-H "Content-Type: application/json" \\<br>
&nbsp;&nbsp;-d '{"url": "https://yourprospect.com", "depth": "standard"}'
</div>

<h2>What you get back</h2>
<div class="features">
  <div class="feature"><h3>🏢 Company Profile</h3><p>Name, industry, size estimate, stage, business model, HQ — scraped and structured.</p></div>
  <div class="feature"><h3>🔧 Tech Stack</h3><p>CRM, hosting, analytics, payments, support tools — detected from the site.</p></div>
  <div class="feature"><h3>📈 Growth Signals</h3><p>Recent funding, hiring patterns, news, and growth indicators.</p></div>
  <div class="feature"><h3>🎯 ICP Fit Score</h3><p>0–100 score with reasoning, calibrated to your ideal customer profile.</p></div>
  <div class="feature"><h3>💡 Pain Hypothesis</h3><p>The specific problem this company likely has — ready to use in outreach.</p></div>
  <div class="feature"><h3>✉️ Opening Line</h3><p>A personalized, non-cringe cold email opener. Not a template — actual reasoning.</p></div>
</div>

<h2>Simple pricing</h2>
<div class="pricing">
  <div class="plan">
    <div class="price">$49</div><div class="period">/month</div>
    <div class="credits">500 credits</div>
    <strong style="display:block;color:#fff;margin-bottom:12px">Starter</strong>
    <a href="https://buy.stripe.com/dRm3coaPAev3bTYawzaZi00">Subscribe →</a>
  </div>
  <div class="plan featured">
    <div class="price">$149</div><div class="period">/month</div>
    <div class="credits">2,500 credits</div>
    <strong style="display:block;color:#fff;margin-bottom:12px">Pro</strong>
    <a href="https://buy.stripe.com/cNi6oA6zkgDbbTYcEHaZi01">Subscribe →</a>
  </div>
</div>
<p style="color:#666;font-size:13px;margin-top:-40px;margin-bottom:60px">Quick depth = 1 credit. Standard = 1 credit. Deep = 3 credits. 24h cache — same domain only billed once.</p>

</div>
<footer><div class="container">EnrichAPI · Built on Claude · <a href="/docs" style="color:#4ade80">API Docs</a></div></footer>
</body>
</html>""")


@app.get("/success", response_class=HTMLResponse, include_in_schema=False)
def success_page():
    return HTMLResponse(content="""<!DOCTYPE html>
<html><head><title>Welcome to EnrichAPI</title>
<style>body{font-family:-apple-system,sans-serif;background:#0a0a0a;color:#e8e8e8;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center}
.box{max-width:500px;padding:40px}.icon{font-size:3rem;margin-bottom:16px}h1{color:#fff;margin-bottom:12px}p{color:#888;margin-bottom:24px}
a{color:#4ade80}</style></head>
<body><div class="box"><div class="icon">🎉</div>
<h1>You're in.</h1>
<p>Check your email for your API key. Then hit <a href="/docs">/docs</a> to make your first call.</p>
<p style="font-size:13px">Questions? Reply to the welcome email.</p>
</div></body></html>""")
