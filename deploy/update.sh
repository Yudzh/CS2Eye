#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=${CS2EYE_DEPLOY_ROOT:-/opt/cs2eye}
config="$root/shared/deploy.conf"
test -f "$config" || { echo "Missing $config; prepare the server first"; exit 1; }
# Root-owned configuration, without application secrets.
source "$config"
: "${CS2EYE_GIT_URL:?Set repository URL in deploy.conf}"
: "${CS2EYE_GIT_BRANCH:?Set production branch in deploy.conf}"
[[ $# -le 1 ]] || { echo 'Usage: cs2eye-deploy [full-commit-sha]'; exit 1; }
git check-ref-format "refs/heads/$CS2EYE_GIT_BRANCH"
exec 8>"$root/update.lock"
flock -n 8 || { echo 'Another update is running'; exit 1; }
repo="$root/repository.git"
if [[ ! -d "$repo" ]]; then
  git init --bare "$repo"
fi
export GIT_TERMINAL_PROMPT=0
git --git-dir="$repo" fetch --no-tags "$CS2EYE_GIT_URL" "+refs/heads/$CS2EYE_GIT_BRANCH:refs/heads/production"
head=$(git --git-dir="$repo" rev-parse refs/heads/production)
sha=${1:-$head}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo 'Use a full 40-character commit SHA'; exit 1; }
git --git-dir="$repo" merge-base --is-ancestor "$sha" "$head" || {
  echo 'Commit is not in production branch history'; exit 1;
}
mkdir -p "$root/releases"
# Each attempt gets a new directory, including retries of the same commit.
release=$(mktemp -d "$root/releases/$sha.XXXXXX")
git --git-dir="$repo" archive "$sha" | tar -x -C "$release"
test -f "$release/deploy/release.sh" || { echo 'Commit has no deployment script'; exit 1; }
printf 'Deploying %s from %s\nRelease directory: %s\n' "$sha" "$CS2EYE_GIT_BRANCH" "$release"
export CS2EYE_DEPLOY_ROOT="$root" CS2EYE_RELEASE="$sha"
export CS2EYE_IMAGE_PREFIX=cs2eye CS2EYE_BUILD_LOCAL=true
bash "$release/deploy/release.sh"
