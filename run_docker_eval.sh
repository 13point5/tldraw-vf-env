#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PRIME_INTELLECT_API_KEY:-}" ]]; then
  echo "PRIME_INTELLECT_API_KEY is required."
  exit 1
fi

tar --exclude=.venv --exclude=outputs --exclude=__pycache__ --exclude='**/node_modules' --exclude='**/dist' -czf - . | docker run --rm -i \
  -e PRIME_INTELLECT_API_KEY="$PRIME_INTELLECT_API_KEY" \
  -e PRIME_API_KEY="$PRIME_INTELLECT_API_KEY" \
  -e PRIME_API_TOKEN="$PRIME_INTELLECT_API_KEY" \
  python:3.13-bookworm bash -lc '
set -euo pipefail

apt-get update && apt-get install -y \
  curl git bash ca-certificates xz-utils \
  && rm -rf /var/lib/apt/lists/*

mkdir -p /work
tar -xzf - -C /work
cd /work

# Install uv + prime CLI
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$PATH:/root/.local/bin"

# Use a container-local venv inside /work
python -m venv /work/.venv
. /work/.venv/bin/activate
uv pip install --upgrade pip
uv pip install verifiers prime

export PYTHONPATH="/work"
export PRIME_API_KEY="${PRIME_INTELLECT_API_KEY:-$PRIME_API_KEY}"
export PRIME_API_TOKEN="${PRIME_INTELLECT_API_KEY:-$PRIME_API_TOKEN}"

# Install environment package into this venv
prime env install tldraw || prime env install --path /work/environments/tldraw

# Run eval (bootstrap will install Node + npm deps + Playwright Chromium)
prime eval run tldraw -m openai/gpt-4.1-mini -n 1 -r 1 \
  -a "{\"validator_url\":\"http://127.0.0.1:5173/validator.html\",\"pool_size\":1,\"headless\":true}"
'
