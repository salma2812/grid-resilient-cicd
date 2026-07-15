#!/usr/bin/env bash
# Manually fire the same repository_dispatch events Member 2's Orchestrator
# sends, without needing the full orchestrator running. Useful for testing
# your CI/CD integration in isolation, and for the live demo.
#
# Usage:
#   GITHUB_REPO=owner/repo GITHUB_TOKEN=ghp_xxx ./simulate_outage.sh high
#   GITHUB_REPO=owner/repo GITHUB_TOKEN=ghp_xxx ./simulate_outage.sh clear

set -euo pipefail

if [ -z "${GITHUB_REPO:-}" ] || [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "Set GITHUB_REPO (owner/repo) and GITHUB_TOKEN (PAT with 'repo' scope) first." >&2
  exit 1
fi

case "${1:-}" in
  high)
    EVENT_TYPE="grid_risk_high"
    ;;
  clear)
    EVENT_TYPE="grid_risk_clear"
    ;;
  *)
    echo "Usage: $0 [high|clear]" >&2
    exit 1
    ;;
esac

echo "Firing repository_dispatch: $EVENT_TYPE -> $GITHUB_REPO"

curl -sf -X POST "https://api.github.com/repos/${GITHUB_REPO}/dispatches" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -d "{\"event_type\": \"${EVENT_TYPE}\"}"

echo "Sent. Check the Actions tab for the 'Grid Risk Listener' run."
