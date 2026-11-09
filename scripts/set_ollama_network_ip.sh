#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <Minikube-to-host IPv4 address>" >&2
  echo 'Find the current route with: minikube ssh "grep host.minikube.internal /etc/hosts"' >&2
  exit 2
fi
if python3 --version >/dev/null 2>&1; then
  python_cmd=(python3)
elif command -v py >/dev/null 2>&1; then
  python_cmd=(py -3)
else
  echo 'Python 3 is required (python3 or the Windows py launcher).' >&2
  exit 1
fi
"${python_cmd[@]}" - "$1" k8s/base/networkpolicy.yaml k8s/base/configmap.yaml <<'PY'
import ipaddress
import re
import sys
from pathlib import Path

ip = ipaddress.IPv4Address(sys.argv[1])
policy_path = Path(sys.argv[2])
policy = policy_path.read_text(encoding="utf-8")
policy, cidr_count = re.subn(
    r"(?m)^(\s*cidr:\s*)\d{1,3}(?:\.\d{1,3}){3}/32\s*$",
    rf"\g<1>{ip}/32",
    policy,
)
if cidr_count != 2:
    raise SystemExit(f"expected two IPv4 /32 Ollama egress entries in {policy_path}, found {cidr_count}")
policy_path.write_text(policy, encoding="utf-8")

config_path = Path(sys.argv[3])
config = config_path.read_text(encoding="utf-8")
config, url_count = re.subn(
    r"(?m)^(\s*OLLAMA_URL:\s*)http://[^\s]+:11434\s*$",
    rf"\g<1>http://{ip}:11434",
    config,
)
if url_count != 1:
    raise SystemExit(f"expected one OLLAMA_URL entry in {config_path}, found {url_count}")
config_path.write_text(config, encoding="utf-8")
print(f"API and indexer Ollama route updated to {ip}:11434 in both manifests.")
PY
