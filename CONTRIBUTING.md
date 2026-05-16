# Contributing to CANarchy

Thanks for your interest in improving CANarchy. This guide is the short
human-facing version of the contributor flow. Day-to-day project rules,
agent-specific workflow, and deeper architectural guidance live in
[`AGENTS.md`](AGENTS.md); please read that file before contributing
non-trivial changes.

## Project shape

* CANarchy is implemented in Python and targets Python 3.12 or newer.
* `uv` is the dependency / environment / build tool.
* The CLI is the project contract; the REPL and TUI are views over the
  same engine. New behaviour goes through the command layer.
* Structured JSON / JSONL output is part of the public surface. Treat the
  output envelope as stable unless the change is intentional and
  documented in `CHANGELOG.md`.

## Local development

```bash
# Sync dependencies and create the project virtualenv.
uv sync

# Install canarchy on your PATH so source edits take effect immediately.
uv tool install --editable .

# Confirm the CLI is wired up.
canarchy --version
canarchy --help

# Run the full test suite.
uv run pytest tests/ -q
```

`uv.lock` is checked in for reproducible resolution. Do not modify it by
hand — let `uv` do that.

## Continuous integration

Every push to `main` and every pull request runs two workflows:

* [`.github/workflows/test.yml`](.github/workflows/test.yml) — `pytest`
  matrix on Python 3.12 and 3.13. Match locally with
  `uv run pytest tests/ -q`.
* [`.github/workflows/lint.yml`](.github/workflows/lint.yml) — `ruff check`
  and `ruff format --check`. Match locally with `uv run ruff check`
  and `uv run ruff format --check`.

## Issues come first

CANarchy uses GitHub Issues as the source of truth for planned work.

* Before starting any non-trivial feature, bug fix, or refactor, check the
  issue tracker for an existing item or open one with clear acceptance
  criteria.
* Comment on the issue to claim it before you start work. This prevents
  duplicate effort.
* Every commit should reference the relevant issue via
  `closes #N`, `fixes #N`, or `refs #N`.

The full rule is in [`AGENTS.md`](AGENTS.md#every-change-must-be-associated-with-an-issue).

## Branches and pull requests

* Work on a dedicated branch named after the issue where practical
  (`issue-NNN-short-slug`).
* Open a pull request when the work is ready — direct pushes to `main`
  are not the default flow.
* Update [`CHANGELOG.md`](CHANGELOG.md) under `[Unreleased]` in the same
  PR that introduces the change.

## What a "ready to merge" PR looks like

Every PR must clear the following gates before it is ready for review:

1. Linked issue referenced in the commit / PR body.
2. Tests pass locally and in CI. New behaviour ships with new tests.
3. `CHANGELOG.md` updated under `[Unreleased]`.
4. Touched design spec under `docs/design/` reflects the implemented
   behaviour (using EARS syntax per [`docs/spec-template.md`](docs/spec-template.md)).
5. Touched test spec under `docs/tests/` reflects the actual coverage
   (using Gherkin Given/When/Then per the same template).
6. If the change affects the command surface, the MCP tool surface, or
   the structured-output schema, `AGENTS.md` and `docs/agents.md` are
   updated.
7. Other docs (architecture, tutorials, `docs/command_spec.md`) do not
   reference behaviour that this PR changes.

See [`AGENTS.md`](AGENTS.md#pr-acceptance-criteria) for the canonical
checklist.

## Style and design

* Favour readability and explicitness over cleverness. Keep modules
  small and focused.
* Prefer pure functions in the engine layer; keep transport adapters
  separate from semantic layers.
* Structured errors carry `code`, `message`, and an actionable `hint`.
  Use `DBC_CACHE_MISS` as the reference for how to write a good hint.
* Don't mix human-readable decoration into JSON or JSONL output. Log to
  stderr; reserve stdout for structured payloads.
* Active-transmit features (anything that writes frames to a real bus)
  must respect the safety controls described in
  [`SECURITY.md`](SECURITY.md) and the relevant design specs.

## Documentation

CANarchy treats documentation as part of the deliverable, not a follow-up.

* Update `docs/command_spec.md` when adding or changing commands.
* Update `docs/event-schema.md` when changing structured-output shapes.
* Tutorials live under `docs/tutorials/`; short task recipes live under
  `docs/cookbook/`.
* The docs site is built with MkDocs in strict mode (`mkdocs.yml`). Any
  new page must be added to the nav.

## Reporting security issues

Please follow [`SECURITY.md`](SECURITY.md) rather than filing a public
issue for security-sensitive reports, particularly anything involving
active transmission on a real vehicle bus.

## Code of conduct

By participating in this project, you agree to abide by the
[Code of Conduct](CODE_OF_CONDUCT.md).
