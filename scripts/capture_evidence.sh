#!/usr/bin/env bash
set -euo pipefail

NS="${NS:-rahbar}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/docs/evidence"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"

capture() {
  local name="$1"; shift
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n\n'
    "$@"
  } >"$OUT/${STAMP}-${name}.txt" 2>&1 || {
    echo "Command failed; see output above." >>"$OUT/${STAMP}-${name}.txt"
    return 1
  }
}

capture pods kubectl get pods -n "$NS" -o wide
capture top-pods kubectl top pods -n "$NS"
capture hpa kubectl get hpa -n "$NS" -o wide
capture endpoints kubectl get endpoints -n "$NS" -o wide
capture rollout kubectl rollout status deployment/api -n "$NS" --timeout=120s
capture rollout-history kubectl rollout history deployment/api -n "$NS"
printf 'Evidence saved under %s\n' "$OUT"
