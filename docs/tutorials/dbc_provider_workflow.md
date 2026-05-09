# Tutorial: Discover and Use Provider-Backed DBC Files

This tutorial walks through the current provider-backed DBC workflow from catalog refresh to capture decoding.

It is useful when you have a candump trace but do not already have the matching DBC file on disk.

## Goal

By the end of this tutorial you will:

* refresh the optional opendbc catalog
* search for likely DBC files
* fetch a DBC into the local cache
* inspect it before use
* decode a capture with a provider ref instead of a local file path
* use `re match-dbc` to rank candidate DBCs against a capture

## Prerequisites

This workflow uses the optional opendbc integration, so it requires network access for the catalog refresh and fetch steps.

The examples below use `tests/fixtures/sample.candump` as the capture source.

## Step 1 — Refresh the Provider Catalog

Populate the local catalog manifest from the configured provider:

```bash
canarchy dbc cache refresh --provider opendbc --json
```

This updates the cached provider manifest under `~/.canarchy/cache/dbc`.

## Step 2 — Search for Candidate DBCs

Search by make, model family, or another keyword:

```bash
canarchy dbc search toyota --provider opendbc --limit 5 --text
```

This returns provider-catalog matches without downloading every DBC file.

## Step 3 — Fetch a DBC Into the Local Cache

Once you have a likely candidate, fetch it by provider ref:

```bash
canarchy dbc fetch opendbc:toyota_tnga_k_pt --json
```

Provider refs can also use the `comma:` alias:

```bash
canarchy dbc fetch comma:toyota_tnga_k_pt --json
```

## Step 4 — Inspect the DBC Before Decoding

Inspect the database metadata directly from the provider ref:

```bash
canarchy dbc inspect opendbc:toyota_tnga_k_pt --json
```

Restrict the result to a single message when needed:

```bash
canarchy dbc inspect opendbc:toyota_tnga_k_pt --message STEER_TORQUE_SENSOR --text
```

Structured output includes `data.dbc_source`, which records the provider, logical DBC name, pinned version, and resolved local cache path.

## Step 5 — Decode a Capture Using the Provider Ref

Use the same provider ref directly with `decode`:

```bash
canarchy decode --file tests/fixtures/sample.candump --dbc opendbc:toyota_tnga_k_pt --json
```

This avoids copying or hard-coding a separate local path.

## Step 6 — Rank Candidate DBCs Against a Capture

If you are not sure which catalog entry fits the capture best, score multiple candidates against the observed arbitration IDs:

```bash
canarchy re match-dbc tests/fixtures/sample.candump --provider opendbc --limit 5 --text
```

To narrow the catalog first by vehicle make:

```bash
canarchy re shortlist-dbc tests/fixtures/sample.candump --make toyota --provider opendbc --limit 5 --text
```

These commands are passive and file-backed. They do not decode payload semantics; they rank candidate DBCs by frequency-weighted arbitration-ID coverage.

## Summary

| Step | Command | Why it matters |
|------|---------|----------------|
| 1 | `dbc cache refresh` | populates the local provider catalog |
| 2 | `dbc search` | finds likely DBC names before fetching |
| 3 | `dbc fetch` | downloads and caches a specific DBC |
| 4 | `dbc inspect` | verifies the schema before use |
| 5 | `decode --dbc opendbc:<name>` | decodes without a separate local path |
| 6 | `re match-dbc` / `re shortlist-dbc` | ranks likely DBC fits against a capture |

For the full command contract, see the [Command Spec](../command_spec.md).
