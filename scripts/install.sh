#!/usr/bin/env bash
#
# My Gateway AI — self-host installer.
# Bootstraps the full stack (Redis, Qdrant, gateway) with one command.
#
# Usage:
#   ./scripts/install.sh          # interactive setup
#   ./scripts/install.sh -y       # non-interactive, takes defaults
#
set -euo pipefail

BOLD="$(tput bold 2>/dev/null || true)"
RESET="$(tput sgr0 2>/dev/null || true)"
GREEN="$(tput setaf 2 2>/dev/null || true)"
RED="$(tput setaf 1 2>/dev/null || true)"
YELLOW="$(tput setaf 3 2>/dev/null || true)"

say() { printf "%s%s%s\n" "$BOLD" "$1" "$RESET"; }
ok()   { printf "%s✓%s %s\n" "$GREEN" "$RESET" "$1"; }
err()  { printf "%s✗%s %s\n" "$RED" "$RESET" "$1" >&2; }
warn() { printf "%s!%s %s\n" "$YELLOW" "$RESET" "$1"; }

cwd="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$cwd"

say ""
say "  My Gateway AI — self-host installer"
say "  ────────────────────────────────"
say ""

# ---- Prereqs ----
need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "missing dependency: $1"
    exit 1
  fi
  ok "$1 found"
}

need docker
need git

if ! docker info >/dev/null 2>&1; then
  err "Docker daemon is not running"
  exit 1
fi
ok "Docker daemon reachable"

# ---- Config ----
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
  say "Creating $ENV_FILE ..."
  cp .env.example "$ENV_FILE"
else
  warn "$ENV_FILE already exists — leaving it alone. Delete it to start fresh."
  read -rp "Continue with existing $ENV_FILE? [y/N] " -n 1 -r; echo
  [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi

# ---- Prompts ----
non_interactive="${1:-}"

if [ "$non_interactive" != "-y" ]; then
  read -rp "Gateway API key [auto-generate] (leave empty to auto-generate): " GATEWAY_KEY
  read -rp "Master encryption key (protects user/provider keys) [auto-generate]: " MASTER_KEY
fi

GATEWAY_KEY="${GATEWAY_KEY:-}"
MASTER_KEY="${MASTER_KEY:-}"

if [ -z "$GATEWAY_KEY" ]; then
  GATEWAY_KEY="$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40)"
  ok "generated GATEWAY_API_KEY"
fi
if [ -z "$MASTER_KEY" ]; then
  MASTER_KEY="$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 48)"
  ok "generated GATEWAY_MASTER_KEY"
fi

# Inject into .env (idempotent — only sets when not present or when value is the default)
if grep -q '^GATEWAY_API_KEY=' "$ENV_FILE"; then
  sed -i.bak "s|^GATEWAY_API_KEY=.*|GATEWAY_API_KEY=$GATEWAY_KEY|" "$ENV_FILE"
else
  echo "GATEWAY_API_KEY=$GATEWAY_KEY" >> "$ENV_FILE"
fi
if grep -q '^GATEWAY_MASTER_KEY=' "$ENV_FILE"; then
  sed -i.bak "s|^GATEWAY_MASTER_KEY=.*|GATEWAY_MASTER_KEY=$MASTER_KEY|" "$ENV_FILE"
else
  echo "GATEWAY_MASTER_KEY=$MASTER_KEY" >> "$ENV_FILE"
fi
rm -f "$ENV_FILE.bak"

warn "Write these down NOW — they will not be shown again and are needed to log in:"
printf "  GATEWAY_API_KEY   = %s%s%s\n" "$BOLD" "$GATEWAY_KEY" "$RESET"
printf "  GATEWAY_MASTER_KEY= %s%s%s\n" "$BOLD" "$MASTER_KEY" "$RESET"
say ""

# ---- Boot ----
say "Pulling images and starting the stack..."
docker compose pull
docker compose up -d --build --remove-orphans

ok "gateway is starting; dashboard will be at http://localhost:8000/dashboard"
ok "health check: http://localhost:8000/health"
ok "open the dashboard and log in with GATEWAY_API_KEY"
say ""
