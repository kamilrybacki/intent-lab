#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# ── Colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BOLD}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[  OK]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# ── Pre-flight checks ───────────────────────────────────────────────
command -v docker  >/dev/null 2>&1 || fail "docker is not installed"
command -v python3 >/dev/null 2>&1 || fail "python3 is not installed"

echo
echo -e "${BOLD}============================================================${NC}"
echo -e "${BOLD}  Intent Engineering — One-Shot Launcher${NC}"
echo -e "${BOLD}============================================================${NC}"
echo

# ── 1. Start Redis via docker compose ────────────────────────────────
info "Starting Redis (docker compose up -d) ..."
if docker compose up -d 2>/dev/null; then
    ok "Redis is running."
else
    warn "docker compose failed — trying 'docker-compose' (v1) ..."
    docker-compose up -d || fail "Cannot start Redis. Check docker-compose.yml."
    ok "Redis is running (compose v1)."
fi

# ── 2. Build the Claude Code Docker image ────────────────────────────
info "Building Docker image 'claude-code:local' ..."
docker build -t claude-code:local . | tail -1
ok "Docker image ready."

# ── 3. Install Python dependencies ──────────────────────────────────
info "Installing Python dependencies ..."
pip install -q -r requirements.txt
ok "Dependencies installed."

# ── 4. Run the experiment ────────────────────────────────────────────
echo
info "Launching experiment runner ..."
echo
python3 run_experiment.py "$@"
