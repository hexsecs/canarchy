#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
site_root="$repo_root/site"

rm -rf "$site_root"
uv run mkdocs build --strict
cp "$repo_root/index.html" "$site_root/index.html"

if [[ ! -f "$site_root/index.html" ]]; then
  echo "missing published homepage: $site_root/index.html" >&2
  exit 1
fi

if [[ ! -f "$site_root/docs/index.html" ]]; then
  echo "missing docs homepage: $site_root/docs/index.html" >&2
  exit 1
fi

printf 'Built Pages site in %s\n' "$site_root"
