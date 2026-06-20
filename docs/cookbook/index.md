# Cookbook

Short, task-oriented recipes for common CANarchy workflows. Each recipe
is one page and either runs against a fixture checked into the repository
or names the controlled lab setup required for active transport work.
Recipes link back to the full tutorial or command spec where it applies.

For longer walkthroughs, see the [Tutorials](../tutorials/index.md) page.

## Capture and triage

* [Filter for a single arbitration ID or PGN](filter-pgn.md)
* [Analyze a capture from a UTHP / TCAT appliance](analyze-tcat-capture.md)
* [Compare two captures for DM1 fault diffs](compare-dm1-faults.md)
* [Build a virtual CAN loop for offline testing](virtual-can-loop.md)
* [Verify a PCAN interface in 30 seconds](verify-pcan-interface.md)
* [Verify a Vector interface in 30 seconds](verify-vector-interface.md)
* [Verify a Kvaser interface in 30 seconds](verify-kvaser-interface.md)

## Decoding

* [Decode SPN 110 (engine coolant temperature)](decode-spn-110.md)
* [Match an unknown capture against opendbc](match-dbc-against-capture.md)

## Reverse engineering

* [Find counter signals in a capture](find-counter-signals.md)

## Active fuzzing

* [Fuzz Tesla DI_torque2 vehicle speed](fuzz-tesla-di-torque2-speed.md)

## Datasets and external sources

* [Acquire a bounded dataset slice for offline analysis](acquire-dataset-slice.md)
* [Stream the CANdid dataset into stats](stream-candid-into-stats.md)
* [Stream commaCarSegments CAN data](stream-comma-car-segments.md)

## Agents and MCP

* [Wire CANarchy into Claude Desktop or Claude Code](mcp-claude-integration.md)
