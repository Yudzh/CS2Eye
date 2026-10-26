#!/usr/bin/env bash
set -Eeuo pipefail
# Run from an extracted release directory. Shared configuration lives outside it.
: "${CS2EYE_DEPLOY_ROOT:?Set deployment root}"
: "${CS2EYE_IMAGE_PREFIX:?Set image prefix}"
: "${CS2EYE_RELEASE:?Set commit SHA}"
[[ "$CS2EYE_RELEASE" =~ ^[0-9a-f]{40}$ ]] || { echo 'Release must be a full commit SHA'; exit 1; }
cd "$(dirname "$0")/.."
exec 9>"$CS2EYE_DEPLOY_ROOT/deploy.lock"
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
shared="$CS2EYE_DEPLOY_ROOT/shared"
test -f "$shared/.env.prod"
test -f "$shared/secrets/web.htpasswd"
ln -sfn "$shared/secrets" deploy/secrets
compose=(docker compose --env-file "$shared/.env.prod" -f compose.prod.yml)
if [[ -f "$shared/use-bo3-proxy" ]]; then
  compose+=(-f compose.bo3-proxy.yml)
fi
compose+=(-f compose.release.yml)
if [[ -f "$shared/use-https" ]]; then
  compose+=(--profile https)
fi
"${compose[@]}" config --quiet
if [[ "${CS2EYE_BUILD_LOCAL:-false}" == true ]]; then
  # Build before stopping production; tags are unique to this commit.
  "${compose[@]}" build api webui
else
  "${compose[@]}" pull api bot migrate webui
fi
mkdir -p "$CS2EYE_DEPLOY_ROOT/backups"
chmod 700 "$CS2EYE_DEPLOY_ROOT/backups"
# Back up an existing database before changing its schema. First provisioning
# and restoration of local data are performed separately.
"${compose[@]}" exec -T db sh -c 'pg_isready -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
backup="$CS2EYE_DEPLOY_ROOT/backups/$(date -u +%Y%m%dT%H%M%SZ)-$CS2EYE_RELEASE.dump"
(umask 077; "${compose[@]}" exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$backup")
test -s "$backup"
"${compose[@]}" exec -T db pg_restore --list < "$backup" > /dev/null
# Stop background writers while applying migrations.
"${compose[@]}" stop api bot
resume_on_failure() {
  result=$?
  trap - ERR
  echo 'Deployment failed; trying to restart existing API and bot containers'
  "${compose[@]}" start api bot || true
  exit "$result"
}
trap resume_on_failure ERR
"${compose[@]}" run --rm --no-deps migrate
# Ready-made local AI reports are immutable release data; no LLM runs on the VPS.
"${compose[@]}" run --rm --no-deps migrate python -m cs2eye.deployment.ai_reports import
# Schema/data migrations and forecasts are part of the same release workflow.
# A release is not ready merely because its containers can start.
"${compose[@]}" run --rm --no-deps migrate python -m cs2eye.deployment.prepare
# The database is already running. Do not recreate it as part of an app release.
"${compose[@]}" up -d --no-build --no-deps --wait --wait-timeout 180 api bot webui
if [[ -f "$shared/use-https" ]]; then
  "${compose[@]}" up -d --no-build --no-deps https
fi
"${compose[@]}" exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/ready', timeout=10)"
"${compose[@]}" exec -T api python -m cs2eye.deployment.verify_results
status=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --max-time 15 http://127.0.0.1:18080/)
[[ "$status" == 401 ]] || { echo "Expected authentication challenge, got HTTP $status"; exit 1; }
if [[ -L "$CS2EYE_DEPLOY_ROOT/current" ]]; then
  ln -sfn "$(readlink "$CS2EYE_DEPLOY_ROOT/current")" "$CS2EYE_DEPLOY_ROOT/previous"
fi
ln -sfn "$PWD" "$CS2EYE_DEPLOY_ROOT/current.next"
mv -Tf "$CS2EYE_DEPLOY_ROOT/current.next" "$CS2EYE_DEPLOY_ROOT/current"
echo "Deployed $CS2EYE_RELEASE"
