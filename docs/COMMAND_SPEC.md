# COMMAND_SPEC.md (initial)

## Command Structure

Commands follow a consistent pattern:

```text
canarchy <domain> <action> [args]
```

or

```text
canarchy <action> <object>
```

---

## Core Commands

### capture

Capture CAN traffic.

```bash
canarchy capture <interface> [--jsonl]
```

---

### send

Send CAN frames.

```bash
canarchy send <interface> <id> <data>
```

---

### replay

Replay recorded traffic.

```bash
canarchy replay <file> [--rate <factor>]
```

---

### decode

Decode using DBC.

```bash
canarchy decode <file> --dbc <file>
```

---

## J1939 Commands

### monitor

```bash
canarchy j1939 monitor [--pgn <id>]
```

### decode

```bash
canarchy j1939 decode <file>
```

---

## UDS Commands

### scan

```bash
canarchy uds scan <interface>
```

---

## Reverse Engineering Commands

### signals

```bash
canarchy re signals <file>
```

### counters

```bash
canarchy re counters <file>
```

---

## Output Modes

All commands should support:

* `--json`
* `--jsonl`
* `--table`
* `--raw`

---

## Exit Codes

* 0 success
* 1 user error
* 2 transport error
* 3 decode error
* 4 partial success

---

## Notes

This spec is intentionally minimal and should evolve alongside implementation.
