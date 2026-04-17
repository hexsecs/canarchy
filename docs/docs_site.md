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

Build the static site locally:

```bash
uv run mkdocs build --strict
```

## Source Layout

The docs site pulls from these in-repo sources:

* `docs/index.md` for the docs landing page
* `README.md` surfaced through `docs/overview.md`
* `AGENTS.md` surfaced through `docs/agents.md`
* `docs/architecture.md`, `docs/command_spec.md`, and `docs/tui_plan.md` as direct site pages

This keeps the hosted docs aligned with the current repository state while avoiding a second docs-only repo.

## GitHub Pages

The GitHub Pages workflow builds the MkDocs site on pushes to `main` and deploys the generated `site/` artifact through GitHub Pages.

If the Pages site is not yet enabled in the repository settings, enable GitHub Pages with GitHub Actions as the source.
