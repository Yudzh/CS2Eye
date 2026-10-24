#!/usr/bin/env bash
# Publish completed local AI reports and run the normal VPS deployment.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ $(git branch --show-current) == telegtam-prod ]] || {
  echo 'Switch to telegtam-prod before publishing'; exit 1;
}
reports=src/cs2eye/deployment/ai_report_artifacts
git add --all -- "$reports"
if ! git diff --cached --quiet -- "$reports"; then
  # Commit only reports; do not include unrelated staged or uncommitted code.
  git commit --only -m 'Publish completed AI reports' -- "$reports"
fi
git push origin telegtam-prod
ssh "${CS2EYE_SSH_TARGET:-cs2eye}" cs2eye-deploy
