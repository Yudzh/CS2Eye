#!/usr/bin/env bash
# Run once on an existing production server, from the new source checkout.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo 'Run as root'; exit 1; }
root=${CS2EYE_DEPLOY_ROOT:-/opt/cs2eye}
legacy=${CS2EYE_EXISTING_ROOT:-$root}
cd "$(dirname "$0")/.."
for tool in git docker flock curl tar; do command -v "$tool" >/dev/null; done
docker compose version
project=$(docker inspect cs2eye-prod-db-1 --format '{{index .Config.Labels "com.docker.compose.project"}}')
[[ "$project" == cs2eye-prod ]] || { echo 'Expected existing cs2eye-prod database'; exit 1; }
docker inspect cs2eye-prod-db-1 --format '{{range .Mounts}}{{println .Name}}{{end}}' | grep -qx cs2eye-prod_pg_data
install -d -m 700 "$root/shared" "$root/releases" "$root/backups"
if [[ ! -e "$root/shared/.env.prod" ]]; then
  install -m 600 "$legacy/.env.prod" "$root/shared/.env.prod"
fi
if [[ ! -e "$root/shared/secrets" ]]; then
  cp -a "$legacy/deploy/secrets" "$root/shared/secrets"
fi
chmod 700 "$root/shared/secrets"
test -s "$root/shared/secrets/web.htpasswd"
if [[ ! -e "$root/shared/deploy.conf" ]]; then
  cat > "$root/shared/deploy.conf" <<'EOF'
CS2EYE_GIT_URL=https://github.com/Yudzh/CS2Eye.git
CS2EYE_GIT_BRANCH=telegtam-prod
EOF
fi
files=$(docker inspect cs2eye-prod-api-1 --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}')
if [[ "$files" == *compose.bo3-proxy.yml* ]]; then
  touch "$root/shared/use-bo3-proxy"
fi
if docker inspect cs2eye-prod-https-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  touch "$root/shared/use-https"
fi
install -o root -g root -m 755 deploy/update.sh /usr/local/bin/cs2eye-deploy
echo "Prepared $root. Run cs2eye-deploy to deploy the production branch."
