"""
Stripe billing integration.

Set STRIPE_ENABLED=true and STRIPE_RESTRICTED_KEY_TWOFLOWER to enable live billing.

When live billing is enabled, this module:
  - Creates a Stripe customer on API key generation (create_stripe_customer)
  - Reports usage via Stripe Meters (usage-based), falling back to InvoiceItems
"""

import logging
import os
import time

logger = logging.getLogger(__name__)

STRIPE_ENABLED = os.getenv("STRIPE_ENABLED", "false").lower() == "true"
STRIPE_SECRET_KEY = os.getenv("STRIPE_RESTRICTED_KEY_TWOFLOWER") or os.getenv("STRIPE_SECRET_KEY")

# Price per depth tier in cents
DEPTH_PRICES = {
    "quick": 5,       # $0.05
    "standard": 25,   # $0.25
    "deep": 75,       # $0.75
}

METER_EVENT_NAME = "enrichapi_call"

# Module-level cache for meter availability (avoids repeated failed API calls)
_meter_id: str | None = None
_meter_available: bool | None = None  # None=unknown, True=ok, False=not available


def create_stripe_customer(api_key: str, name: str = "unnamed") -> str | None:
    """
    Create a Stripe customer for a new API key.
    Returns the Stripe customer ID, or None if billing is disabled or fails.
    """
    if not STRIPE_ENABLED:
        return None

    if not STRIPE_SECRET_KEY:
        logger.warning("Stripe enabled but no key configured")
        return None

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        customer = stripe.Customer.create(
            name=name,
            description=f"EnrichAPI — key {api_key[:8]}...",
            metadata={"api_key_prefix": api_key[:8]},
        )
        logger.info("Created Stripe customer %s for api_key=%s...", customer.id, api_key[:8])
        return customer.id
    except Exception as e:
        logger.error("Failed to create Stripe customer: %s", e)
        return None


def _get_or_create_meter() -> str | None:
    """Return the Stripe billing meter ID, creating it if needed. Returns None if unavailable."""
    global _meter_id, _meter_available

    if _meter_available is False:
        return None
    if _meter_id:
        return _meter_id

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        # Check for an existing meter with our event name
        meters = stripe.billing.Meter.list(limit=100)
        for meter in meters.auto_paging_iter():
            if meter.event_name == METER_EVENT_NAME:
                _meter_id = meter.id
                _meter_available = True
                logger.info("Found existing Stripe meter: %s", _meter_id)
                return _meter_id

        # Create a new meter
        meter = stripe.billing.Meter.create(
            display_name="EnrichAPI Calls",
            event_name=METER_EVENT_NAME,
            default_aggregation={"formula": "sum"},
            value_settings={"event_payload_key": "value"},
        )
        _meter_id = meter.id
        _meter_available = True
        logger.info("Created Stripe billing meter: %s", _meter_id)
        return _meter_id
    except Exception as e:
        logger.warning("Stripe billing meters not available (%s) — will use invoice items", e)
        _meter_available = False
        return None


def _report_via_meter(stripe_customer_id: str, depth: str, price_cents: int) -> bool:
    """Report usage via Stripe billing meter event. Returns True on success."""
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        if not _get_or_create_meter():
            return False

        stripe.billing.MeterEvent.create(
            event_name=METER_EVENT_NAME,
            payload={
                "stripe_customer_id": stripe_customer_id,
                "value": str(price_cents),
            },
            timestamp=int(time.time()),
        )
        logger.info(
            "[BILLING] Meter event: customer=%s depth=%s $%.2f",
            stripe_customer_id, depth, price_cents / 100,
        )
        return True
    except Exception as e:
        logger.warning("Meter event failed (%s) — falling back to invoice item", e)
        return False


def _report_via_invoice_item(stripe_customer_id: str, depth: str, price_cents: int) -> bool:
    """Report usage via Stripe pending invoice item (fallback). Returns True on success."""
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        stripe.InvoiceItem.create(
            customer=stripe_customer_id,
            amount=price_cents,
            currency="usd",
            description=f"EnrichAPI {depth} call",
        )
        logger.info(
            "[BILLING] Invoice item: customer=%s depth=%s $%.2f",
            stripe_customer_id, depth, price_cents / 100,
        )
        return True
    except Exception as e:
        logger.error("Invoice item creation failed: %s", e)
        return False


def report_usage(
    api_key: str,
    depth: str,
    cached: bool = False,
    stripe_customer_id: str | None = None,
) -> bool:
    """
    Report a billable API call.

    Returns True if billing succeeded (or was skipped for cached calls).
    In mock mode, always returns True after logging.
    """
    if cached:
        return True

    price_cents = DEPTH_PRICES.get(depth, 25)

    if not STRIPE_ENABLED:
        logger.info(
            "[BILLING MOCK] api_key=%s... depth=%s charge=$%.2f",
            api_key[:8],
            depth,
            price_cents / 100,
        )
        return True

    if not STRIPE_SECRET_KEY:
        logger.warning("Stripe enabled but no key configured — skipping billing")
        return True

    if not stripe_customer_id:
        logger.warning(
            "[BILLING] No Stripe customer for api_key=%s... — skipping", api_key[:8]
        )
        return True

    # Try meter events first, fall back to invoice items
    if _report_via_meter(stripe_customer_id, depth, price_cents):
        return True
    return _report_via_invoice_item(stripe_customer_id, depth, price_cents)
