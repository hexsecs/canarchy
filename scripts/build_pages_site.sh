#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
site_root="$repo_root/site"

rm -rf "$site_root"
uv run mkdocs build --strict

cp "$repo_root/src/homepage/index.html" "$site_root/index.html"
cp "$repo_root/src/homepage/site-brutalist.jsx" "$site_root/site-brutalist.jsx"

if [[ ! -f "$site_root/index.html" ]]; then
  echo "missing published homepage: $site_root/index.html" >&2
  exit 1
fi

if [[ ! -f "$site_root/docs/index.html" ]]; then
  echo "missing docs homepage: $site_root/docs/index.html" >&2
  exit 1
fi

printf 'Built Pages site in %s\n' "$site_root"
