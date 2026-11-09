#!/usr/bin/env bash
set -uo pipefail

NS="${NS:-rahbar}"
TIMEOUT="${TIMEOUT:-3}"
failed=0

pod_for() {
  kubectl get pods -n "$1" -l "$2" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

tcp_check() {
  local pod="$1" container="$2" host="$3" port="$4"
  kubectl exec -n "$NS" "$pod" -c "$container" -- python -c \
    'import socket,sys; s=socket.create_connection((sys.argv[1],int(sys.argv[2])),float(sys.argv[3])); s.close()' \
    "$host" "$port" "$TIMEOUT" >/dev/null 2>&1
}

dns_check() {
  local pod="$1" container="$2" name="$3"
  kubectl exec -n "$NS" "$pod" -c "$container" -- python -c \
    'import socket,sys; socket.getaddrinfo(sys.argv[1],None)' "$name" >/dev/null 2>&1
}

record() {
  local label="$1" expected="$2"; shift 2
  if "$@"; then actual=PASS; else actual=FAIL; fi
  if [[ "$actual" == "$expected" ]]; then
    printf 'PASS  %s (%s as expected)\n' "$label" "$actual"
  else
    printf 'FAIL  %s (expected %s, got %s)\n' "$label" "$expected" "$actual"
    failed=1
  fi
}

api_pod="$(pod_for "$NS" 'app=api')"
ui_pod="$(pod_for "$NS" 'app=ui')"
controller_pod="$(pod_for ingress-nginx 'app.kubernetes.io/component=controller')"
if [[ -z "$api_pod" || -z "$ui_pod" || -z "$controller_pod" ]]; then
  echo "FAIL  required api, ui, or ingress controller pod is missing"
  exit 2
fi

debug_pod="rahbar-netcheck-indexer"
cleanup() { kubectl delete pod -n "$NS" "$debug_pod" --ignore-not-found --wait=false >/dev/null 2>&1 || true; }
trap cleanup EXIT
kubectl delete pod -n "$NS" "$debug_pod" --ignore-not-found --wait=true >/dev/null
kubectl run "$debug_pod" -n "$NS" --restart=Never --image=rahbar-indexer:dev \
  --image-pull-policy=IfNotPresent --labels=app=indexer \
  --overrides='{"apiVersion":"v1","spec":{"serviceAccountName":"indexer","automountServiceAccountToken":false,"securityContext":{"runAsNonRoot":true,"runAsUser":10001,"runAsGroup":10001,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"rahbar-netcheck-indexer","image":"rahbar-indexer:dev","command":["python","-c","import time; time.sleep(600)"],"securityContext":{"allowPrivilegeEscalation":false,"readOnlyRootFilesystem":true,"capabilities":{"drop":["ALL"]}},"resources":{"requests":{"cpu":"10m","memory":"32Mi"},"limits":{"cpu":"100m","memory":"64Mi"}},"volumeMounts":[{"name":"tmp","mountPath":"/tmp"}]}],"volumes":[{"name":"tmp","emptyDir":{}}]}}' >/dev/null
kubectl wait -n "$NS" --for=condition=Ready "pod/$debug_pod" --timeout=90s >/dev/null || {
  echo "FAIL  indexer network-check pod did not become ready"
  exit 2
}

record "Ingress controller -> UI:8080" PASS kubectl exec -n ingress-nginx "$controller_pod" -- \
  wget -q -T "$TIMEOUT" -O /dev/null "http://ui.$NS.svc.cluster.local:8080/"
record "Ingress controller -> API:8000" PASS kubectl exec -n ingress-nginx "$controller_pod" -- \
  wget -q -T "$TIMEOUT" -O /dev/null "http://api.$NS.svc.cluster.local:8000/healthz"
record "UI -> API:8000" PASS kubectl exec -n "$NS" "$ui_pod" -- \
  wget -q -T "$TIMEOUT" -O /dev/null "http://api.$NS.svc.cluster.local:8000/healthz"
record "API -> kube-dns" PASS dns_check "$api_pod" api "chroma.$NS.svc.cluster.local"
record "Indexer -> kube-dns" PASS dns_check "$debug_pod" rahbar-netcheck-indexer "chroma.$NS.svc.cluster.local"
# The nginx UI image does not contain Python; use its own `getent` binary instead
# of the Python-based helper used by the API and indexer images.
record "UI -> kube-dns" PASS kubectl exec -n "$NS" "$ui_pod" -- \
  getent hosts "api.$NS.svc.cluster.local"
record "API -> Chroma:8000" PASS tcp_check "$api_pod" api "chroma.$NS.svc.cluster.local" 8000
record "Indexer -> Chroma:8000" PASS tcp_check "$debug_pod" rahbar-netcheck-indexer \
  "chroma.$NS.svc.cluster.local" 8000
record "API -> Redis:6379" PASS tcp_check "$api_pod" api "redis.$NS.svc.cluster.local" 6379
record "Indexer -> Redis:6379 is denied" FAIL tcp_check "$debug_pod" rahbar-netcheck-indexer \
  "redis.$NS.svc.cluster.local" 6379
record "UI -> Chroma:8000 is denied" FAIL kubectl exec -n "$NS" "$ui_pod" -- \
  wget -q -T "$TIMEOUT" -O /dev/null "http://chroma.$NS.svc.cluster.local:8000/api/v2/heartbeat"

if [[ -n "${OLLAMA_HOST_IP:-}" ]]; then
  record "API -> Ollama:${OLLAMA_PORT:-11434}" PASS tcp_check "$api_pod" api "$OLLAMA_HOST_IP" "${OLLAMA_PORT:-11434}"
  record "Indexer -> Ollama:${OLLAMA_PORT:-11434}" PASS tcp_check "$debug_pod" rahbar-netcheck-indexer "$OLLAMA_HOST_IP" "${OLLAMA_PORT:-11434}"
else
  echo "FAIL  API and indexer -> Ollama:11434 (set OLLAMA_HOST_IP to the host.minikube.internal IP)"
  failed=1
fi

exit "$failed"
