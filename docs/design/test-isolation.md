# Design Spec: Test Isolation

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | None (test infrastructure) |
| Primary area | Testing, safety |
| Related specs | `docs/design/active-transmit-safety.md`, `docs/design/uds-active-workflows.md` |
| Issues | #531 (found during the evaluation tracked in #532) |

## Goal

Running `pytest` must not read, write, or transmit anything belonging to the
person running it. A contributor should get that guarantee by default,
without opting in, and a test that breaks it should fail immediately and say
which test it was.

## User-Facing Motivation

Before this, the suite depended on the machine it ran on, in three ways that
were each demonstrated rather than theorised:

1. **It wrote to real application state.** A single full run left two fuzz
   campaign directories in the operator's real `~/.canarchy/findings`, from
   two `fuzz guided` tests that ran an active campaign without passing
   `--findings-dir`. Thirty-eight had accumulated on the evaluation machine.
2. **It read real configuration.** With a `~/.canarchy/config.toml` setting
   `interface = "udp_multicast"` and a `default_interface`, nine tests failed
   and python-can logged `UdpMulticastBus was not properly shut down` — the
   suite had opened a real multicast socket.
3. **Its default pointed at hardware.** `transport_backend_config()` defaults
   to the `python-can` backend on `socketcan`. On a machine with a live
   interface, a test that reaches a bus with no configuration at all would
   open the real one.

The third point is why configuration isolation alone is insufficient, and
the first is why a bus guard alone is insufficient. Both are needed.

The deeper problem is diagnostic: when the suite's result depends on the
developer's configuration, a failure means "something is different about
this machine" rather than "the code is wrong", and a pass means nothing
about anyone else's machine.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-TISO-01` | Ubiquitous | The test suite shall resolve `Path.home()` to a per-test temporary directory by default, so configuration, caches, session state, plugin state, metadata overrides, and fuzz findings never resolve to the operator's own. |
| `REQ-TISO-02` | Ubiquitous | The test suite shall remove every `CANARCHY_*` environment variable from a test's environment by default. |
| `REQ-TISO-03` | Ubiquitous | The system shall redirect state paths that captured `Path.home()` at import time, which the `HOME` redirection alone does not move. |
| `REQ-TISO-04` | Unwanted behaviour | If a test opens a real CAN interface through `python_can.Bus`, the system shall fail that test immediately with a message naming the test and the requested interface. |
| `REQ-TISO-05` | Optional feature | Where python-can's in-process `virtual` interface is requested, the system shall permit it, since it opens no socket and reaches no hardware. |
| `REQ-TISO-06` | Optional feature | Where a test is marked `integration`, the system shall skip isolation and the bus guard for it. |
| `REQ-TISO-07` | Ubiquitous | The system shall exclude `integration`-marked tests from the default run and require explicit selection with `-m integration`. |
| `REQ-TISO-08` | Ubiquitous | Isolation shall not conceal configuration-sensitive product behaviour: tests covering configuration precedence shall continue to set a configured default interface through their own explicit fixtures. |
| `REQ-TISO-09` | Ubiquitous | The suite shall produce the same result whether or not the operator has a `~/.canarchy/config.toml`. |

## Design

Two autouse fixtures in `tests/conftest.py`, both active by default.

### `isolate_canarchy_state`

Redirects `HOME` and `USERPROFILE` to a per-test temporary directory
(`REQ-TISO-01`) and deletes every `CANARCHY_*` variable (`REQ-TISO-02`).

The redirection is done **through the environment**, not by patching
`Path.home`. `Path.home()` resolves `~` via `HOME` on POSIX and `USERPROFILE`
on Windows, so setting them moves in-process code *and* subprocess-based
tests such as the stdio MCP server, which inherit the environment. Patching
`Path.home` to a fixed value would instead override a test that sets up its
own `HOME` — `tests/test_session.py::workspace` does exactly that — silently
pointing the code under test somewhere the test never wrote to.

A handful of modules bind `Path.home()` into module-level constants at import
time, before any fixture runs, so the environment redirection does not move
them. These are re-pointed explicitly (`REQ-TISO-03`):

| Module | Constant |
|--------|----------|
| `canarchy.dbc_cache` | `_CACHE_ROOT`, `_CONFIG_PATH` |
| `canarchy.skills_cache` | `_CACHE_ROOT`, `_CONFIG_PATH` |
| `canarchy.j1587_metadata` | `_PID_OVERRIDES_DEFAULT` |
| `canarchy.j1939_metadata` | `_SPN_OVERRIDES_DEFAULT` |
| `canarchy.j2497_metadata` | `_MID_OVERRIDES_DEFAULT` |

### `forbid_real_can_bus`

`python_can.Bus(...)` in `PythonCanBackend._open_bus` is the single place a
real interface is opened, so the guard wraps exactly that (`REQ-TISO-04`).

The `virtual` interface is allowed through (`REQ-TISO-05`): it is an
in-process message queue with no socket and no hardware, the CAN equivalent
of the localhost server the web tests bind. Every other interface —
`socketcan`, `udp_multicast`, `pcan`, `vector`, `kvaser` — reaches a real bus
or the network and is refused.

Tests that legitimately exercise the python-can backend patch
`PythonCanBackend._open_bus` and never reach the guard, so it costs them
nothing.

### What isolation deliberately does not do

`REQ-TISO-08` is the constraint that shapes the rest. Making the suite green
by hiding configuration-sensitivity would be worse than the original state:
#530 — where a configured default interface turned a reference catalog lookup
into unacknowledged active bus probing — was found *because* a test inherited
real configuration and failed.

So the `uds services` regressions from #530 continue to set a configured
default interface, through their own `_load_user_config` patches and
`patch.dict(os.environ, ...)`, rather than inheriting whatever the developer
happens to have. Isolation makes that coverage deliberate and identical on
every machine; it does not remove it. This is verified by reintroducing the
#530 defect and confirming the regressions still fail under isolation
(`TEST-TISO-14`).

## Error Cases

| Condition | Behaviour |
|-----------|-----------|
| A test opens a non-`virtual` bus | `AssertionError` naming the test node id, the channel, and the interface, plus the four ways to fix it |
| A test is marked `integration` | Isolation and the guard both stand down; the test is deselected unless `-m integration` is passed |
| python-can is not installed | The guard stands down; there is no bus to open |

## Out Of Scope

* Sandboxing filesystem access outside `~/.canarchy` — tests legitimately
  write to `tmp_path` and read repository fixtures.
* Blocking all network access. The web tests bind a localhost server on
  purpose; the guard targets CAN interfaces specifically, which is where the
  operator-visible risk is.
* Retrofitting every existing test onto shared fixtures. Tests that already
  isolate correctly are left alone.
