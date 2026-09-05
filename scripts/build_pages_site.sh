#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
site_root="$repo_root/site"

rm -rf "$site_root"
uv run mkdocs build --strict

cp "$repo_root/src/homepage/index.html" "$site_root/index.html"
cp "$repo_root/src/homepage/site.css" "$site_root/site.css"
cp "$repo_root/src/homepage/og-card.png" "$site_root/og-card.png"

site_url="https://hexsecs.github.io/canarchy"

# On a GitHub *project* page this file is served from /canarchy/robots.txt,
# which crawlers do not treat as authoritative (only the host root counts),
# so the sitemaps below must also be submitted directly to search engines
# (e.g. Google Search Console / Bing Webmaster Tools). The file still serves
# SEO tooling that probes it and becomes authoritative if the site ever
# moves to a custom domain served from the root.
cat > "$site_root/robots.txt" <<EOF
User-agent: *
Allow: /

Sitemap: $site_url/sitemap.xml
Sitemap: $site_url/docs/sitemap.xml
EOF

cat > "$site_root/sitemap.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>$site_url/</loc>
  </url>
</urlset>
EOF

if [[ ! -f "$site_root/index.html" ]]; then
  echo "missing published homepage: $site_root/index.html" >&2
  exit 1
fi

if [[ ! -f "$site_root/docs/index.html" ]]; then
  echo "missing docs homepage: $site_root/docs/index.html" >&2
  exit 1
fi

if [[ ! -f "$site_root/site.css" ]]; then
  echo "missing homepage stylesheet: $site_root/site.css" >&2
  exit 1
fi

# The homepage must be readable without executing JavaScript: crawlers that do
# not run scripts, and every social scraper, only ever see this payload.
for marker in "J1939" "stream-first runtime" "MCP SERVER"; do
  if ! grep -qF "$marker" "$site_root/index.html"; then
    echo "homepage is missing crawlable content: $marker" >&2
    exit 1
  fi
done

if grep -qiE 'babel|react\.(development|production)' "$site_root/index.html"; then
  echo "homepage ships a browser-side compiler or framework build" >&2
  exit 1
fi

printf 'Built Pages site in %s\n' "$site_root"
