#!/usr/bin/env bash
# [LAPTOP] Update the Pi: push to GitHub and pull on the Pi, or copy with rsync when there is no remote.
# Then install the node requirements on the Pi.
# Usage: node/tools/deploy.sh [--rsync] [host]     (host defaults to icu-pi)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
mode=git
if [ "${1:-}" = "--rsync" ]; then mode=rsync; shift; fi
host="${1:-icu-pi}"
PIP='cd ~/icu-fusion && .venv/bin/pip install -q -r node/requirements.txt -r node/requirements-pi.txt'

if [ "$mode" = git ]; then
    if [ -z "$(git -C "$ROOT" remote)" ]; then
        echo "This repo has no git remote. Either add one (see docs/HARDWARE_DAY.md) or run: $0 --rsync $host" >&2
        exit 1
    fi
    git -C "$ROOT" push
    # shellcheck disable=SC2029  # $PIP is meant to expand here, on the laptop
    ssh "$host" "cd ~/icu-fusion && git pull --ff-only && $PIP"
else
    # Copies the working tree; never copies secrets, venvs, data or build output.
    rsync -az --delete \
        --exclude '.git/' --exclude '.env' --exclude 'dashboard/.env' --exclude '.venv/' \
        --exclude 'node_modules/' --exclude 'dashboard/dist/' --exclude 'broker/passwd' --exclude 'broker/data/' \
        --exclude 'server/*.db*' --exclude '__pycache__/' --exclude 'test-results/' --exclude '.pytest_cache/' \
        "$ROOT/" "$host:icu-fusion/"
    # shellcheck disable=SC2029
    ssh "$host" "$PIP"
fi
echo "deployed to $host"
