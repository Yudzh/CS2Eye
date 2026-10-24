#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
existing=$(git config --get core.hooksPath || true)
if [[ -n "$existing" && "$existing" != .githooks ]]; then
  echo "Existing hooks path $existing must be integrated before installing report delivery"
  exit 1
fi
if [[ -x .git/hooks/pre-commit ]]; then
  echo 'An existing pre-commit hook must be integrated before installing report delivery'
  exit 1
fi
chmod +x .githooks/pre-commit
git config core.hooksPath .githooks
echo 'Completed local AI reports will be included automatically when committing'
