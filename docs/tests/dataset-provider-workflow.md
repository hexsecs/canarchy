# Test Spec: Dataset Provider Workflow

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/dataset-provider-workflow.md` |
| Issues | #216, #220 |
| Test module | `tests/test_dataset_provider.py` |

---

## Test Cases

### TEST-DATASET-STREAM-01: Stream HCRL CSV To JSONL With Chunk Metadata

```gherkin
Given a small HCRL CSV fixture with six CAN frames
When the operator streams it as JSONL with chunk size 2 and a provider ref
Then six frame events are emitted
And frame offsets are monotonic
And chunk indexes advance at the configured boundary
And the provider ref is preserved in dataset provenance metadata
```

**Fixture:** `tests/fixtures/dataset_hcrl_sample.csv`

### TEST-DATASET-STREAM-02: Stream HCRL CSV To Candump

```gherkin
Given a small HCRL CSV fixture with six CAN frames
When the operator streams it as candump to a destination file
Then six candump lines are written
And each line uses timestamped candump syntax
```

**Fixture:** `tests/fixtures/dataset_hcrl_sample.csv`

### TEST-DATASET-STREAM-03: Reject Invalid Chunk Size

```gherkin
Given a valid HCRL CSV fixture
When the operator requests a stream with chunk size 0
Then the command fails with `INVALID_CHUNK_SIZE`
```

**Fixture:** `tests/fixtures/dataset_hcrl_sample.csv`

### TEST-DATASET-STREAM-04: CLI Streams JSONL To Stdout

```gherkin
Given a small HCRL CSV fixture with six CAN frames
When the operator runs `canarchy datasets stream` with JSONL output and no destination
Then stdout contains six JSONL frame events
And stdout does not contain a wrapping result envelope
```

**Fixture:** `tests/fixtures/dataset_hcrl_sample.csv`

### TEST-DATASET-STREAM-05: CLI JSON Summary Mode

```gherkin
Given a small HCRL CSV fixture with six CAN frames
When the operator runs `canarchy datasets stream --json`
Then stdout contains a standard JSON result envelope
And the result reports frame count and chunk count
And frame events are not emitted to stdout
```

**Fixture:** `tests/fixtures/dataset_hcrl_sample.csv`

---

## Traceability

| Requirement | Tests |
|-------------|-------|
| REQ-DATASET-STREAM-01 | TEST-DATASET-STREAM-01, TEST-DATASET-STREAM-02, TEST-DATASET-STREAM-04 |
| REQ-DATASET-STREAM-02 | TEST-DATASET-STREAM-01, TEST-DATASET-STREAM-02 |
| REQ-DATASET-STREAM-03 | TEST-DATASET-STREAM-01, TEST-DATASET-STREAM-04 |
| REQ-DATASET-STREAM-04 | TEST-DATASET-STREAM-01, TEST-DATASET-STREAM-04 |
| REQ-DATASET-STREAM-05 | TEST-DATASET-STREAM-03 |
| REQ-DATASET-STREAM-06 | Covered by existing malformed HCRL CSV conversion tests in `tests/test_dataset_provider.py` |

---

## Not Tested

- Remote provider-specific streaming adapters are not tested because this increment only streams local downloaded dataset files.
- Live-bus replay is not tested because active replay is intentionally deferred.
- Network access is not tested; all tests use checked-in fixtures.
