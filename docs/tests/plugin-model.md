# Test Spec: Plugin Model

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/plugin-model.md` |
| Test file | `tests/test_plugins.py` |

---

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|---------------------|----------|
| `REQ-PLUGIN-01` | Registry builds with all three built-in RE processors registered | `TEST-PLUGIN-01` |
| `REQ-PLUGIN-02` | `get_processor` returns the registered processor by name | `TEST-PLUGIN-02` |
| `REQ-PLUGIN-03` | `get_processor` returns None for an unknown name | `TEST-PLUGIN-03` |
| `REQ-PLUGIN-04` | Duplicate processor name raises `PLUGIN_DUPLICATE` | `TEST-PLUGIN-04` |
| `REQ-PLUGIN-05` | Incompatible `api_version` raises `PLUGIN_INCOMPATIBLE` | `TEST-PLUGIN-05` |
| `REQ-PLUGIN-06` | Object not satisfying the protocol raises `PLUGIN_INVALID` | `TEST-PLUGIN-06` |
| `REQ-PLUGIN-07` | `reset_registry()` causes the next `get_registry()` call to rebuild | `TEST-PLUGIN-07` |
| `REQ-PLUGIN-08` | `list_processors()` returns name and api_version for each processor | `TEST-PLUGIN-08` |
| `REQ-PLUGIN-09` | `list_sinks()` and `list_input_adapters()` return empty lists initially | `TEST-PLUGIN-09` |
| `REQ-PLUGIN-10` | Sink duplicate name raises `PLUGIN_DUPLICATE` | `TEST-PLUGIN-10` |
| `REQ-PLUGIN-11` | Input adapter duplicate name raises `PLUGIN_DUPLICATE` | `TEST-PLUGIN-11` |
| `REQ-PLUGIN-12` | Built-in `counter-candidates` processor produces correct output shape | `TEST-PLUGIN-12` |
| `REQ-PLUGIN-13` | Built-in `entropy-candidates` processor produces correct output shape | `TEST-PLUGIN-13` |
| `REQ-PLUGIN-14` | Built-in `signal-analysis` processor produces correct output shape | `TEST-PLUGIN-14` |
| `REQ-PLUGIN-15` | `re signals` CLI command routes through registry and returns valid output | `TEST-PLUGIN-15` |
| `REQ-PLUGIN-16` | `re counters` CLI command routes through registry and returns valid output | `TEST-PLUGIN-16` |
| `REQ-PLUGIN-17` | `re entropy` CLI command routes through registry and returns valid output | `TEST-PLUGIN-17` |
| `REQ-PLUGIN-18` | Third-party processor registered manually is discoverable and callable | `TEST-PLUGIN-18` |
| `REQ-PLUGIN-19` | `ProcessorResult` warnings list is present even when empty | `TEST-PLUGIN-19` |

---

## Test Cases

### TEST-PLUGIN-01 — Default registry contains all three built-in RE processors

```gherkin
Given  a freshly reset plugin registry
When   get_registry() is called
Then   processors named 'counter-candidates', 'entropy-candidates', and 'signal-analysis' shall be registered
```

---

### TEST-PLUGIN-02 — get_processor returns the processor by exact name

```gherkin
Given  the default registry
When   get_processor('signal-analysis') is called
Then   the returned object shall have name == 'signal-analysis' and api_version == '1'
```

---

### TEST-PLUGIN-03 — get_processor returns None for unknown name

```gherkin
Given  the default registry
When   get_processor('nonexistent-processor') is called
Then   the return value shall be None
```

---

### TEST-PLUGIN-04 — Duplicate processor registration raises PLUGIN_DUPLICATE

```gherkin
Given  a fresh PluginRegistry
And    a minimal processor with name 'test-proc' has been registered
When   a second processor with name 'test-proc' is registered
Then   a PluginError with code 'PLUGIN_DUPLICATE' shall be raised
```

---

### TEST-PLUGIN-05 — Incompatible api_version raises PLUGIN_INCOMPATIBLE

```gherkin
Given  a fresh PluginRegistry
When   a processor with api_version '99' is registered
Then   a PluginError with code 'PLUGIN_INCOMPATIBLE' shall be raised
And    the error message shall name the plugin and the required api_version
```

---

### TEST-PLUGIN-06 — Object missing required members raises PLUGIN_INVALID

```gherkin
Given  a fresh PluginRegistry
When   an object that does not implement ProcessorPlugin (missing 'process') is registered
Then   a PluginError with code 'PLUGIN_INVALID' shall be raised
```

---

### TEST-PLUGIN-07 — reset_registry causes rebuild on next access

```gherkin
Given  get_registry() has been called and the registry is cached
When   reset_registry() is called
And    get_registry() is called again
Then   the returned registry shall be a new instance
And    it shall contain the built-in processors
```

---

### TEST-PLUGIN-08 — list_processors returns name and api_version

```gherkin
Given  the default registry
When   list_processors() is called
Then   the result shall be a list of dicts each with 'name' and 'api_version' keys
And    each entry's api_version shall equal '1'
```

---

### TEST-PLUGIN-09 — list_sinks and list_input_adapters return empty by default

```gherkin
Given  a fresh PluginRegistry with no sinks or input adapters registered
When   list_sinks() and list_input_adapters() are called
Then   both shall return empty lists
```

---

### TEST-PLUGIN-10 — Duplicate sink name raises PLUGIN_DUPLICATE

```gherkin
Given  a fresh PluginRegistry
And    a sink named 'test-sink' has been registered
When   a second sink named 'test-sink' is registered
Then   a PluginError with code 'PLUGIN_DUPLICATE' shall be raised
```

---

### TEST-PLUGIN-11 — Duplicate input adapter name raises PLUGIN_DUPLICATE

```gherkin
Given  a fresh PluginRegistry
And    an input adapter named 'test-adapter' has been registered
When   a second input adapter named 'test-adapter' is registered
Then   a PluginError with code 'PLUGIN_DUPLICATE' shall be raised
```

---

### TEST-PLUGIN-12 — counter-candidates processor produces correct output shape

```gherkin
Given  a list of CanFrames with a detectable counter field
When   get_registry().get_processor('counter-candidates').process(frames) is called
Then   the result shall be a ProcessorResult
And    result.candidates shall be a non-empty list
And    each candidate dict shall have 'arbitration_id', 'start_bit', 'bit_length', and 'score' keys
And    result.metadata['analysis'] shall equal 'counter_detection'
```

---

### TEST-PLUGIN-13 — entropy-candidates processor produces correct output shape

```gherkin
Given  a list of CanFrames with varying payload bytes
When   get_registry().get_processor('entropy-candidates').process(frames) is called
Then   the result shall be a ProcessorResult
And    result.metadata['analysis'] shall equal 'entropy_ranking'
```

---

### TEST-PLUGIN-14 — signal-analysis processor produces correct output shape

```gherkin
Given  a list of CanFrames with a detectable signal field
When   get_registry().get_processor('signal-analysis').process(frames) is called
Then   the result shall be a ProcessorResult
And    result.metadata shall contain 'analysis_by_id' and 'low_sample_ids' keys
And    result.metadata['analysis'] shall equal 'signal_inference'
```

---

### TEST-PLUGIN-15 — re signals CLI command produces valid JSON output

```gherkin
Given  a candump fixture with known signal fields
When   canarchy re signals <fixture> --json is run
Then   exit code shall be 0
And    output['ok'] shall be True
And    output['data'] shall contain 'candidates' and 'analysis_by_id'
```

---

### TEST-PLUGIN-16 — re counters CLI command produces valid JSON output

```gherkin
Given  a candump fixture with a known counter field
When   canarchy re counters <fixture> --json is run
Then   exit code shall be 0
And    output['ok'] shall be True
And    output['data']['candidates'] shall be non-empty
```

---

### TEST-PLUGIN-17 — re entropy CLI command produces valid JSON output

```gherkin
Given  a candump fixture with non-constant payload bytes
When   canarchy re entropy <fixture> --json is run
Then   exit code shall be 0
And    output['ok'] shall be True
And    output['data']['candidates'] shall be a list
```

---

### TEST-PLUGIN-18 — Manually registered third-party processor is discoverable

```gherkin
Given  a fresh PluginRegistry
And    a custom processor with name 'custom-proc' and api_version '1' is registered
When   get_processor('custom-proc') is called
Then   the returned processor shall be the registered instance
And    calling process(frames) shall return a ProcessorResult
```

---

### TEST-PLUGIN-19 — ProcessorResult warnings is always a list

```gherkin
Given  any processor producing no warnings
When   process() is called and result.warnings is inspected
Then   result.warnings shall be an empty list, not None
```
