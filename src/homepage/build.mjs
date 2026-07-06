// Build the published CANarchy homepage.
//
// 1. Precompile site-brutalist.jsx -> dist/site-brutalist.js (Babel, JSX only).
// 2. Vendor React + ReactDOM production UMD builds into dist/.
// 3. Prerender the rendered DOM into dist/index.html so crawlers and social
//    scrapers get real content without executing JavaScript; the client still
//    loads React and re-renders for the interactive, viewport-responsive page.
//
// The dist/ output is committed so the GitHub Pages build only has to copy it
// (no Node, npm, or headless browser needed in CI). Run `node build.mjs` after
// editing site-brutalist.jsx, index.html, or bumping React.

import { transformFileSync } from '@babel/core';
import puppeteer from 'puppeteer-core';
import { createServer } from 'node:http';
import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, 'dist');
mkdirSync(dist, { recursive: true });

const reactUmd = join(here, 'node_modules', 'react', 'umd', 'react.production.min.js');
const reactDomUmd = join(here, 'node_modules', 'react-dom', 'umd', 'react-dom.production.min.js');

// Resolve a Chromium binary. Prefer Playwright's install (present in CI images
// via setup), fall back to a PUPPETEER/CHROME env override.
function findChromium() {
  const candidates = [
    process.env.CANARCHY_CHROMIUM,
    process.env.PUPPETEER_EXECUTABLE_PATH,
    '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
    '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell',
  ].filter(Boolean);
  for (const c of candidates) if (existsSync(c)) return c;
  return null;
}

// 1. Compile JSX (preset-react only — keep it a classic global script).
const { code } = transformFileSync(join(here, 'site-brutalist.jsx'), {
  presets: [['@babel/preset-react', { runtime: 'classic' }]],
  comments: false,
  compact: false,
});
writeFileSync(join(dist, 'site-brutalist.js'), code);

// 2. Vendor React.
copyFileSync(reactUmd, join(dist, 'react.production.min.js'));
copyFileSync(reactDomUmd, join(dist, 'react-dom.production.min.js'));

// 3. Prerender. Serve dist/ over loopback so relative script src resolves, load
//    a copy of index.html with an empty #root, snapshot after React renders.
const template = readFileSync(join(here, 'index.html'), 'utf8');
const emptyPage = template.replace('<!--PRERENDER-->', '');

const server = createServer((req, res) => {
  const url = (req.url || '/').split('?')[0];
  if (url === '/' || url === '/index.html') {
    res.writeHead(200, { 'content-type': 'text/html' });
    res.end(emptyPage);
    return;
  }
  const file = join(dist, url.replace(/^\//, ''));
  if (existsSync(file)) {
    res.writeHead(200, { 'content-type': 'application/javascript' });
    res.end(readFileSync(file));
    return;
  }
  res.writeHead(404);
  res.end('not found');
});

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const port = server.address().port;

const chromium = findChromium();
let prerendered = null;

if (chromium) {
  const browser = await puppeteer.launch({
    executablePath: chromium,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu'],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
    await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'networkidle0', timeout: 30000 });
    await page.waitForFunction(
      () => document.getElementById('root')?.children.length > 0,
      { timeout: 15000 },
    );
    prerendered = await page.$eval('#root', (el) => el.innerHTML);
  } finally {
    await browser.close();
  }
} else {
  console.warn('[build] No Chromium found — writing client-only page (no prerender).');
}

server.close();

const finalHtml = template.replace('<!--PRERENDER-->', prerendered ?? '');
writeFileSync(join(dist, 'index.html'), finalHtml);

const bytes = prerendered ? prerendered.length : 0;
console.log(`[build] dist/index.html written (${bytes} prerendered bytes in #root)`);
console.log('[build] dist/site-brutalist.js, react.production.min.js, react-dom.production.min.js vendored');
