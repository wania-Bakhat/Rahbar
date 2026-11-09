#!/usr/bin/env bash
set -euo pipefail

NS="${NS:-rahbar}"
SOURCE="${CORPUS_SOURCE:-corpus/raw}"
POD="corpus-loader-$(date +%s)"
if [[ ! -d "$SOURCE" ]]; then
  echo "Corpus directory not found: $SOURCE (run make fetch first)." >&2
  exit 2
fi
if ! compgen -G "$SOURCE/*.pdf" >/dev/null; then
  echo "No PDFs found in $SOURCE." >&2
  exit 2
fi

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  namespace: $NS
  labels:
    app: corpus-loader
spec:
  restartPolicy: Never
  serviceAccountName: indexer
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: loader
      image: busybox:1.36.1
      command: ["sh", "-c", "sleep 3600"]
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      resources:
        requests:
          cpu: 10m
          memory: 32Mi
        limits:
          cpu: 100m
          memory: 64Mi
      volumeMounts:
        - name: corpus
          mountPath: /corpus
  volumes:
    - name: corpus
      persistentVolumeClaim:
        claimName: corpus-data
EOF

cleanup() { kubectl delete pod -n "$NS" "$POD" --ignore-not-found --wait=false >/dev/null 2>&1 || true; }
trap cleanup EXIT
kubectl wait -n "$NS" --for=condition=Ready "pod/$POD" --timeout=120s
# Git Bash/MSYS can rewrite the `namespace/pod:/path` destination as a local
# Windows path before kubectl sees it. Disable that conversion for this call;
# kubectl and the Go runtime accept the relative source path on Windows.
MSYS_NO_PATHCONV=1 kubectl cp "$SOURCE/." "$NS/$POD:/corpus/"
echo "Loaded $(find "$SOURCE" -maxdepth 1 -type f | wc -l | tr -d ' ') files into PVC corpus-data."
