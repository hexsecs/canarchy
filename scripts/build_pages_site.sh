#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
site_root="$repo_root/site"

rm -rf "$site_root"
uv run mkdocs build --strict

# The homepage is prerendered and its assets vendored into src/homepage/dist by
# `node src/homepage/build.mjs` (committed output), so this build only copies
# them — no Node, npm, or headless browser needed here. Regenerate dist after
# editing the homepage source.
homepage_dist="$repo_root/src/homepage/dist"
if [[ ! -f "$homepage_dist/index.html" ]]; then
  echo "missing prerendered homepage: $homepage_dist/index.html (run: node src/homepage/build.mjs)" >&2
  exit 1
fi
cp "$homepage_dist/index.html" "$site_root/index.html"
cp "$homepage_dist/site-brutalist.js" "$site_root/site-brutalist.js"
cp "$homepage_dist/react.production.min.js" "$site_root/react.production.min.js"
cp "$homepage_dist/react-dom.production.min.js" "$site_root/react-dom.production.min.js"
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

printf 'Built Pages site in %s\n' "$site_root"
