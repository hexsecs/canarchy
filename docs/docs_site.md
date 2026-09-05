# Docs Workflow

CANarchy publishes its full documentation site from the same repository as the codebase using `mkdocs-material` and GitHub Pages.

## Local Preview

Install the docs toolchain:

```bash
uv sync --group docs
```

Run the local docs server:

```bash
uv run mkdocs serve
```

Build the full GitHub Pages site locally:

```bash
bash scripts/build_pages_site.sh
```

This produces:

* `site/index.html` as the custom GitHub Pages landing page built from `src/homepage/index.html` and `src/homepage/site.css`
* `site/docs/` as the MkDocs-built documentation site

## Source Layout

The docs site pulls from these in-repo sources:

* `src/homepage/index.html` and `src/homepage/site.css` for the GitHub Pages landing page
* `docs/index.md` for the docs landing page published at `/docs/`
* `README.md` surfaced through `docs/overview.md`
* `AGENTS.md` surfaced through `docs/agents.md`
* `docs/architecture.md`, `docs/command_spec.md`, and `docs/tui_plan.md` as direct site pages

This keeps the hosted docs aligned with the current repository state while avoiding a second docs-only repo.

## Landing Page

The landing page is static HTML and CSS with no build step. Its content must be
present in the HTML payload itself: crawlers that do not execute JavaScript, and
every social scraper, never see script-rendered markup. `scripts/build_pages_site.sh`
fails the build if the published page loses that content or picks up a
browser-side framework or compiler, and `tests/test_homepage.py` asserts the same
from the source file.

Client-side scripting is limited to the mobile navigation toggle and the
`pip install` copy button; both are progressive enhancements over markup that
works without them. Responsive behaviour lives in media queries in
`src/homepage/site.css`, which uses the breakpoints 1100px (desktop), 760px
(tablet), 430px, and 390px. Update the release version and issue tag in the hero
and install sections of `src/homepage/index.html` on each release.

## Mermaid Diagrams

The docs site supports Mermaid code fences for architecture and flow diagrams.

Use standard Mermaid fenced blocks:

```text
```mermaid
flowchart TD
  A[Source] --> B[Target]
```
```

Mermaid rendering is configured in `mkdocs.yml` and initialized by `docs/javascripts/mermaid.js`.

The site theme also supports light and dark mode through Material for MkDocs, following system preferences by default and allowing manual toggling in the site header. Mermaid diagrams derive their theme from the active site palette.

## GitHub Pages

The GitHub Pages workflow builds the full Pages artifact on pushes to `main` and deploys the generated `site/` directory through GitHub Pages.

The published structure is:

* `/` for the custom homepage
* `/docs/` for the MkDocs documentation site

If the Pages site is not yet enabled in the repository settings, enable GitHub Pages with GitHub Actions as the source.
