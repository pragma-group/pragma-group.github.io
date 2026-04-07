#!/usr/bin/env bash
# Rsync public site content to the PRAGMA deploy path (same as GitHub Actions deploy-rsync workflow).
# Syncs only: icons/, jtc1/, pics/, and index.html (not the whole repo).
#
# Usage (from repo root):
#   DEPLOY_PATH=/var/www/html/paperflow/site/pragma SSH_HOST=example.com SSH_USER=you ./scripts/deploy-rsync.sh
#
# Uses your default SSH identity or ~/.ssh/config for the host.
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:?set DEPLOY_PATH to remote site root (e.g. /var/www/html/paperflow/site/pragma)}"
SSH_HOST="${SSH_HOST:?}"
SSH_USER="${SSH_USER:?}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

REMOTE="${SSH_USER}@${SSH_HOST}:${DEPLOY_PATH}"
RSYNC=(rsync -avz -e ssh)

echo "Rsync public paths → ${REMOTE}/"
"${RSYNC[@]}" --delete icons/ "${REMOTE}/icons/"
"${RSYNC[@]}" --delete jtc1/ "${REMOTE}/jtc1/"
"${RSYNC[@]}" --delete pics/ "${REMOTE}/pics/"
"${RSYNC[@]}" index.html "${REMOTE}/index.html"
echo "Rsync complete."
