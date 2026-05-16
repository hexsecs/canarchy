<!--
Thanks for contributing to CANarchy. Please fill in the sections below.
The PR acceptance gates live in AGENTS.md and CONTRIBUTING.md.
-->

## Summary

<!-- Short description of the change. Reference the linked issue. -->

Closes #

## Changes

<!-- Bullet list of the user-visible changes. Describe what changed, not
which files were edited. -->

-

## Test plan

<!-- How was this verified? Include the commands you ran and any manual
checks against fixtures. -->

- [ ] `uv run python -m unittest discover -s tests -v`
- [ ] `uv run ruff check`
- [ ] Manual run against a representative fixture or live interface

## Documentation

<!-- Tick every box that applies. PRs that change behaviour must update
the matching docs in the same PR, not as a follow-up. -->

- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] `docs/command_spec.md` updated (if the command surface changed)
- [ ] `docs/event-schema.md` updated (if the structured-output shape changed)
- [ ] Touched `docs/design/` spec updated (EARS syntax)
- [ ] Touched `docs/tests/` spec updated (Gherkin Given/When/Then)
- [ ] `AGENTS.md` / `docs/agents.md` updated (if agent workflows changed)
- [ ] `mkdocs.yml` nav updated (if any new docs pages were added)

## Safety

<!-- Only if this PR introduces or changes active-bus behaviour. -->

- [ ] Active-transmit commands require `--ack-active`
- [ ] `SECURITY.md` reviewed against the new behaviour
