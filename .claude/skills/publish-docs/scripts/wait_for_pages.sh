#!/usr/bin/env bash
# Wait for the GitHub Pages build of HEAD, then check the live index links each
# given file. Usage: wait_for_pages.sh <file>...
set -u
repo=arthur-fung/afung-docs
site=https://arthur-fung.github.io/afung-docs
head=$(git rev-parse --short=7 HEAD)

for _ in $(seq 1 48); do
  s=$(gh api "repos/$repo/pages/builds/latest" --jq '"\(.commit[0:7]) \(.status)"' 2>/dev/null || true)
  if [ "${s%% *}" = "$head" ]; then
    case "${s#* }" in
      built) echo "build: $head built"; break ;;
      errored) echo "build: $head ERRORED"
               gh api "repos/$repo/pages/builds/latest" --jq '.error.message'; exit 1 ;;
    esac
  fi
  sleep 10
done
[ "${s%% *}" = "$head" ] && [ "${s#* }" = built ] || { echo "build: timed out (last: $s)"; exit 1; }

index=$(curl -s "$site/?nocache=$(date +%s)")
rc=0
for f in "$@"; do
  page="${f%.md}"; page="${page%.html}.html"
  if grep -q "href=\"/afung-docs/$page\"" <<<"$index"; then
    echo "index: ok   $page ($(curl -s -o /dev/null -w '%{http_code}' "$site/$page"))"
  else
    echo "index: MISSING $page"; rc=1
  fi
done
exit $rc
