# Security Policy

CANarchy is a research toolkit for defensive analysis of CAN traffic. This
document covers how to report security concerns and how the project
treats active-bus operations.

## Reporting a security concern

Please do not file a public issue for reports that involve:

* an undisclosed flaw in CANarchy itself
* sensitive findings about a specific vehicle or fleet
* anything that may affect a system in production use

Open a private security advisory through the GitHub interface for this
repository, or contact the maintainers via the address listed on the
project page. Please include:

* a clear description of the concern
* steps to reproduce in a lab environment
* the affected CANarchy version (`canarchy --version`)
* any logs or captures that help triage (with personal data removed)

A maintainer will acknowledge receipt and follow up with a planned
response timeline.

## Supported versions

Only the most recent minor release receives fixes by default. Older
versions may be patched at the maintainers' discretion when the fix is
straightforward.

## Active-bus operations

CANarchy can transmit on a connected CAN interface. Commands that do so
are documented as "active" and are gated by the `--ack-active` flag and
an interactive confirmation prompt by default.

When using active commands:

* Run them on a lab bus, a bench harness, or a virtual interface first.
* Confirm the target before transmitting.
* Keep capture logs of every active session for later review.

Do not run active commands against a vehicle that is in motion, that
carries passengers, or that you are not authorised to test.

Fuzzing workflows are intentionally not exposed in the current CLI while
the active-transmit safety design is being completed. See
`CHANGELOG.md` and the project roadmap for status.

## Scope

This policy covers the CANarchy CLI, library, MCP server, and the
project documentation. Upstream dependencies (for example `python-can`
and `cantools`) should be reported to their own maintainers.
