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

## External-service operations

Most CANarchy workflows run entirely offline. A small number of features
can contact an external service, and they are off by default and opt-in:

* `re suggest --llm <provider>` sends signal-candidate metadata to an
  external LLM for name enrichment. It requires explicit confirmation
  (`--yes`, a `YES` reply, or `CANARCHY_LLM_NONINTERACTIVE=1`), is never
  reachable through the MCP server, and transmits **only** candidate
  metadata — arbitration ids, bit ranges, observed value ranges, change
  rates, and the offline heuristic names. It never sends raw payload
  bytes. Every such invocation records an `external_enrichment` note and
  an `EXTERNAL_SERVICE_CALLED` warning in the output envelope.
* DBC and dataset provider fetches (`dbc fetch`, `datasets fetch`)
  download files over the network from the configured provider.

Treat any capture-derived metadata as potentially sensitive: review what
a feature sends before enabling an external-service path on data from a
real vehicle or fleet, and prefer the offline heuristics when in doubt.

## Scope

This policy covers the CANarchy CLI, library, MCP server, and the
project documentation. Upstream dependencies (for example `python-can`
and `cantools`) should be reported to their own maintainers.
