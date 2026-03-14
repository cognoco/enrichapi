#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# test_enrich.sh — smoke test for EnrichAPI
#
# Usage:
#   ENRICH_API_KEY="your-key" ./test_enrich.sh
#   ENRICH_API_KEY="your-key" BASE_URL="https://yourapp.onrender.com" ./test_enrich.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${ENRICH_API_KEY:-}"
TARGET_URL="${TARGET_URL:-https://linear.app}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ PASS${NC} — $1"; }
fail() { echo -e "${RED}✗ FAIL${NC} — $1"; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}── $1 ──${NC}"; }

if [[ -z "$API_KEY" ]]; then
  echo -e "${RED}Error:${NC} Set ENRICH_API_KEY before running this script."
  echo "  Example: ENRICH_API_KEY='your-key' ./test_enrich.sh"
  exit 1
fi

echo -e "${BOLD}EnrichAPI smoke test${NC}"
echo "  Base URL : $BASE_URL"
echo "  Target   : $TARGET_URL"
echo "  Key      : ${API_KEY:0:8}..."

# ── 1. Health check ───────────────────────────────────────────────────────────
section "1. Health check"
HEALTH=$(curl -sf "$BASE_URL/health")
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")
if [[ "$STATUS" == "ok" ]]; then
  pass "Health endpoint returned status=ok"
else
  fail "Unexpected health response: $HEALTH"
fi

# ── 2. Auth rejection ─────────────────────────────────────────────────────────
section "2. Auth: missing API key"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/enrich" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}')
if [[ "$HTTP_CODE" == "401" ]]; then
  pass "Missing key → 401"
else
  fail "Expected 401, got $HTTP_CODE"
fi

# ── 3. Auth rejection: bad key ────────────────────────────────────────────────
section "3. Auth: invalid API key"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/enrich" \
  -H "X-API-Key: bad-key-xyz" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}')
if [[ "$HTTP_CODE" == "401" ]]; then
  pass "Bad key → 401"
else
  fail "Expected 401, got $HTTP_CODE"
fi

# ── 4. Quick enrichment ───────────────────────────────────────────────────────
section "4. Quick enrichment"
echo -e "${YELLOW}Calling Claude — this may take a few seconds...${NC}"
QUICK=$(curl -sf -X POST "$BASE_URL/enrich" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"$TARGET_URL\", \"depth\": \"quick\"}")

COMPANY_NAME=$(echo "$QUICK" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['company'].get('name',''))" 2>/dev/null || echo "")
if [[ -n "$COMPANY_NAME" ]]; then
  pass "Quick enrichment returned company.name = \"$COMPANY_NAME\""
else
  fail "Quick enrichment missing company.name. Response: $(echo "$QUICK" | python3 -m json.tool 2>/dev/null || echo "$QUICK")"
fi

# ── 5. Standard enrichment with ICP ──────────────────────────────────────────
section "5. Standard enrichment with ICP"
echo -e "${YELLOW}Calling Claude — this may take 5–10 seconds...${NC}"
STANDARD=$(curl -sf -X POST "$BASE_URL/enrich" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"$TARGET_URL\",
    \"depth\": \"standard\",
    \"icp\": {
      \"description\": \"B2B SaaS, 10-500 employees, dev tools\",
      \"ideal_roles\": [\"CTO\", \"Head of Engineering\"]
    },
    \"offer_context\": \"Developer workflow automation\"
  }")

PAIN=$(echo "$STANDARD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('pain_hypothesis','')[:80])" 2>/dev/null || echo "")
ANGLE=$(echo "$STANDARD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('outreach_angle','')[:80])" 2>/dev/null || echo "")
DEPTH=$(echo "$STANDARD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['metadata']['depth'])" 2>/dev/null || echo "")

if [[ "$DEPTH" == "standard" ]]; then
  pass "metadata.depth = standard"
else
  fail "Expected depth=standard, got: $DEPTH"
fi
if [[ -n "$PAIN" ]]; then
  pass "pain_hypothesis present: \"${PAIN}...\""
else
  echo -e "${YELLOW}⚠  pain_hypothesis empty (may depend on ICP context)${NC}"
fi

# ── 6. Cache hit (second call same domain+depth) ──────────────────────────────
section "6. Cache hit"
SECOND=$(curl -sf -X POST "$BASE_URL/enrich" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"$TARGET_URL\", \"depth\": \"quick\"}")

# Second call should return same company name instantly
COMPANY_NAME_2=$(echo "$SECOND" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['company'].get('name',''))" 2>/dev/null || echo "")
if [[ "$COMPANY_NAME_2" == "$COMPANY_NAME" ]]; then
  pass "Cache hit — same result returned for second call"
else
  echo -e "${YELLOW}⚠  Cache may have returned different name (check manually)${NC}"
fi

# ── 7. Usage endpoint ─────────────────────────────────────────────────────────
section "7. Usage stats"
USAGE=$(curl -sf "$BASE_URL/keys/usage" -H "X-API-Key: $API_KEY")
CALLS_TODAY=$(echo "$USAGE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['calls_today'])" 2>/dev/null || echo "")
if [[ -n "$CALLS_TODAY" ]] && [[ "$CALLS_TODAY" -ge 1 ]]; then
  pass "Usage endpoint — calls_today = $CALLS_TODAY"
else
  fail "Usage endpoint returned unexpected data: $USAGE"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}${GREEN}All tests passed.${NC}"
echo ""
echo -e "${BOLD}Sample quick result:${NC}"
echo "$QUICK" | python3 -m json.tool 2>/dev/null || echo "$QUICK"
