#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Prod image healthcheck tests.
#
# Verifies the production Docker image so the Coolify deploy gate stops failing:
#   T-H1  the prod target builds
#   T-H2  curl is present in the image (Coolify's gate runs curl in-container)
#   T-H3  the baked-in Docker HEALTHCHECK points at /healthz, not /api/health
#   T-H4  the container reaches "healthy" and /healthz answers {"status":"ok"}
#
# NOTE: the prod stage in the Dockerfile is named `prod` (not `production`),
# so the build target is `prod`. The image tag stays `lacabrona-bk-healthtest`.
# ---------------------------------------------------------------------------

IMAGE="lacabrona-bk-healthtest"
CONTAINER="lacabrona-bk-healthtest-run"
TARGET="prod"

# Run from the repo root (this script lives in scripts/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

failures=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; failures=$((failures + 1)); }

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker image rm -f "$IMAGE" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# --- T-H1: build the prod target ------------------------------------------
echo "== T-H1: docker build --target $TARGET =="
if docker build --target "$TARGET" -t "$IMAGE" .; then
  pass "T-H1 prod image builds"
else
  fail "T-H1 prod image failed to build"
  # Without an image the remaining checks cannot run.
  echo
  echo "RESULT: $failures check(s) failed"
  exit 1
fi

# --- T-H2: curl exists in the image ---------------------------------------
echo "== T-H2: curl present in image =="
if docker run --rm --entrypoint sh "$IMAGE" -c "command -v curl" >/dev/null 2>&1; then
  pass "T-H2 curl is installed"
else
  fail "T-H2 curl is missing from the image"
fi

# --- T-H3: HEALTHCHECK references /healthz and not /api/health ------------
echo "== T-H3: HEALTHCHECK targets /healthz =="
hc="$(docker inspect --format '{{json .Config.Healthcheck.Test}}' "$IMAGE")"
echo "  Healthcheck.Test = $hc"
if [[ "$hc" == *"/healthz"* && "$hc" != *"/api/health"* ]]; then
  pass "T-H3 healthcheck points at /healthz (and not /api/health)"
else
  fail "T-H3 healthcheck does not correctly reference /healthz"
fi

# --- T-H4: container becomes healthy and /healthz responds ----------------
echo "== T-H4: end-to-end healthy + /healthz body =="
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" \
  -e ENVIRONMENT=test \
  -e CORS_ORIGINS=http://localhost \
  "$IMAGE" >/dev/null

status="unknown"
for _ in $(seq 1 60); do
  status="$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo unknown)"
  if [[ "$status" == "healthy" ]]; then
    break
  fi
  if [[ "$status" == "unhealthy" ]]; then
    break
  fi
  sleep 1
done

if [[ "$status" == "healthy" ]]; then
  pass "T-H4a container reached healthy"
else
  fail "T-H4a container did not reach healthy (last status: $status)"
  echo "  --- container logs ---"
  docker logs "$CONTAINER" 2>&1 | tail -30 || true
fi

body="$(docker exec "$CONTAINER" curl -fsS http://localhost:8000/healthz 2>/dev/null || true)"
echo "  /healthz body = $body"
if [[ "$body" == '{"status":"ok"}' ]]; then
  pass "T-H4b /healthz returned {\"status\":\"ok\"}"
else
  fail "T-H4b /healthz did not return expected body"
fi

echo
if [[ "$failures" -eq 0 ]]; then
  echo "RESULT: all checks passed"
  exit 0
else
  echo "RESULT: $failures check(s) failed"
  exit 1
fi
