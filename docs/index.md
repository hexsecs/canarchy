# CANarchy Docs

CANarchy is a stream-first CAN analysis and manipulation runtime designed for automation, security research, and agent-driven workflows.

Every command emits a [canonical event stream](event-schema.md) — structured, pipeable, and machine-readable. The CLI is the interface. JSONL is the wire format. J1939 is treated as a first-class workflow, not a plugin.

This docs site is the project documentation portal hosted from the same repository as the code.

Start here:

* Operators: [Getting Started](getting_started.md), [Event Schema](event-schema.md), [Command Spec](command_spec.md)
* Demos: [J1939 Heavy Vehicle Analysis](demo_j1939_heavy_vehicle.md), [Generate and Capture](demo_generate_and_capture.md)
* Developers: [Architecture](architecture.md), [Docs Workflow](docs_site.md)
* Agents: [Agent Guide](agents.md)

Site goals:

* keep the event schema and CLI contract explicit and current
* keep code and docs versioned together
* make operator, developer, and agent workflows easy to find
