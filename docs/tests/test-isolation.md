# Test Spec: Test Isolation

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | [`docs/design/test-isolation.md`](../design/test-isolation.md) |
| Implementation | `tests/conftest.py`, `tests/test_isolation.py` |
| Issues | #531 |

## Safe Default Test Command

```sh
uv run pytest tests/ -q
```

This is the command to use, and it is safe on a machine with a real
`~/.canarchy` and real CAN hardware: state is redirected to a temporary
directory, `CANARCHY_*` variables are cleared, a real bus cannot be opened,
and `integration`-marked tests are deselected.

To run the tests that deliberately use the real environment:

```sh
uv run pytest tests/ -q -m integration
```

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-TISO-01` | `TEST-TISO-01`, `TEST-TISO-02`, `TEST-TISO-07` |
| `REQ-TISO-02` | `TEST-TISO-03` |
| `REQ-TISO-03` | `TEST-TISO-06` |
| `REQ-TISO-04` | `TEST-TISO-08`, `TEST-TISO-09`, `TEST-TISO-10`, `TEST-TISO-12` |
| `REQ-TISO-05` | `TEST-TISO-11` |
| `REQ-TISO-06` | `TEST-TISO-15` |
| `REQ-TISO-07` | `TEST-TISO-13`, `TEST-TISO-15` |
| `REQ-TISO-08` | `TEST-TISO-14`, plus the `uds services` regressions in `docs/tests/uds-active-workflows.md` |
| `REQ-TISO-09` | `TEST-TISO-16` |

## Representative Test Cases

### `TEST-TISO-01`..`07` — state redirection

```gherkin
Scenario: TEST-TISO-01 — home is disposable
  When  any unit test runs
  Then  Path.home() shall be a temporary directory
  And   it shall exist

Scenario: TEST-TISO-02 — HOME and Path.home() agree
  When  any unit test runs
  Then  Path(os.environ["HOME"]) shall equal Path.home()
  # Subprocess-based tests inherit HOME rather than in-process patches, so
  # the two must not diverge.

Scenario: TEST-TISO-03 — no CANARCHY_* leaks in
  Given the developer has CANARCHY_DEFAULT_INTERFACE set in their shell
  When  any unit test runs
  Then  no environment variable starting with CANARCHY_ shall be visible

Scenario: TEST-TISO-04 — the user's config reads as empty
  Given the developer has a ~/.canarchy/config.toml
  When  transport._load_user_config() is called from a unit test
  Then  it shall return an empty mapping

Scenario: TEST-TISO-05 — no default interface is inherited
  When  transport.default_can_interface() is called from a unit test
  Then  it shall return None
  # This is the setting behind #530.

Scenario: TEST-TISO-06 — import-time paths are redirected
  When  a unit test reads dbc_cache._CACHE_ROOT, dbc_cache._CONFIG_PATH,
        skills_cache._CACHE_ROOT, or skills_cache._CONFIG_PATH
  Then  each shall be relative to the temporary home
  # These captured Path.home() at import, before any fixture ran.

Scenario: TEST-TISO-07 — fuzz findings stay inside the fake home
  When  a unit test resolves the default fuzz findings directory
  Then  it shall be relative to the temporary home
  # A full run used to leave two campaign directories in the real one.
```

**Fixture:** none; asserts against the autouse fixtures themselves.

### `TEST-TISO-08`..`12` — the CAN bus guard

```gherkin
Scenario: TEST-TISO-08 — socketcan is refused
  When  a unit test calls python_can.Bus(channel="can0", interface="socketcan")
  Then  an AssertionError shall be raised
  And   its message shall contain "tried to open a real CAN bus"

Scenario: TEST-TISO-09 — udp_multicast is refused
  When  a unit test calls python_can.Bus(interface="udp_multicast", ...)
  Then  an AssertionError shall be raised
  # This is the interface that actually opened a socket during the #532
  # evaluation.

Scenario: TEST-TISO-10 — the refusal names the offending test
  When  the guard refuses a bus
  Then  the message shall contain the pytest node id of that test

Scenario: TEST-TISO-11 — the in-process virtual bus is allowed
  When  a unit test calls python_can.Bus(interface="virtual", ...)
  Then  a real python-can virtual bus shall be returned
  And   it shall shut down cleanly
  # `virtual` is an in-process queue: no socket, no hardware.

Scenario: TEST-TISO-12 — the guard surfaces through the backend
  Given a PythonCanBackend configured for socketcan
  When  a unit test calls capture("can0")
  Then  it shall raise rather than reach a real interface
```

**Fixture:** none; uses `canarchy.transport` directly.

### `TEST-TISO-13`, `TEST-TISO-15` — the integration marker

```gherkin
Scenario: TEST-TISO-13 — integration tests are deselected by default
  Given a test file with one ordinary test and one marked `integration`
  When  pytest runs it with the repository configuration and no -m flag
  Then  1 test shall pass and 1 shall be deselected

Scenario: TEST-TISO-15 — integration tests run when selected
  Given the same file
  When  pytest runs it with -m integration
  Then  the marked test shall run
  And   the marker shall be registered, so -W error::PytestUnknownMarkWarning passes
```

**Fixture:** a generated test file under `tmp_path`, run in a pytest
subprocess with `-c pyproject.toml`. The `-c` matters: pytest takes its
rootdir from the test file's location, so a file under `tmp_path` would
otherwise load neither the marker nor the default `-m 'not integration'`.

### `TEST-TISO-14` — isolation does not mask the #530 defect

```gherkin
Scenario: TEST-TISO-14 — a reintroduced defect is still caught
  Given the #530 guard is removed from prepare_args
  When  the `uds services` regressions run under full isolation
  Then  they shall fail
```

**Fixture:** none. This is a **manual verification**, recorded here rather
than automated — a permanent test that reverts a product fix would be
self-defeating. Performed when this isolation landed: removing the
`prepare_args` guard caused nine `uds services` tests to fail under
isolation, confirming the coverage survives. Re-run it by hand if the
isolation fixtures change shape.

### `TEST-TISO-16` — identical results with and without operator config

```gherkin
Scenario: TEST-TISO-16 — the suite does not depend on the machine
  Given a ~/.canarchy/config.toml setting interface = "udp_multicast"
        and default_interface = "vcan-operator"
  When  the full suite runs
  Then  the result shall match a run with no config present
  And   no real bus shall be opened
```

**Fixture:** a temporary HOME containing a representative operator
`config.toml`. **Manual verification**, recorded rather than automated: the
full suite is run twice, once with `HOME` pointing at that directory and
once normally. Before this work the configured run produced 9 failures and a
`UdpMulticastBus was not properly shut down` warning; both runs now report
1713 passed, 1 skipped.

## Not Tested, And Why

* **Real hardware behaviour.** The guard prevents it by design. Anything
  needing a real interface is `integration`-marked and run deliberately by an
  operator.
* **Windows path resolution.** `USERPROFILE` is set alongside `HOME`, but CI
  runs on Linux, so the Windows branch of `Path.home()` is unexercised.
* **Concurrent runs sharing a home.** Each test gets its own temporary
  directory, so there is nothing to contend over.
* **That every existing test is isolated by construction.** The fixtures are
  autouse, so the property is structural; `TEST-TISO-16` checks the outcome
  at suite level rather than per test.
