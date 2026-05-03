# Test Spec: Dataset Provider Workflow

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/dataset-provider-workflow.md` |
| Issues | #216, #220, #233 |
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

### TEST-DATASET-REPLAY-01: Remote Candump Replay Without Local File

```gherkin
Given a mocked remote candump HTTP response
When the operator replays the remote URL
Then candump frames are emitted to stdout
And no complete local dataset file is required
```

**Fixture:** mocked `requests.get` response in `tests/test_dataset_provider.py`

### TEST-DATASET-REPLAY-02: Catalog Ref Replay JSON Summary

```gherkin
Given the CANdid catalog entry defines default replay metadata
When the operator runs `canarchy datasets replay catalog:candid --json`
Then stdout contains a standard JSON result envelope
And the result identifies `catalog:candid` and the default replay file
And frame records are not interleaved into the JSON output
```

**Fixture:** mocked `requests.get` response in `tests/test_dataset_provider.py`

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
| REQ-DATASET-REPLAY-01 | TEST-DATASET-REPLAY-01 |
| REQ-DATASET-REPLAY-02 | TEST-DATASET-REPLAY-02 |
| REQ-DATASET-REPLAY-03 | TEST-DATASET-REPLAY-01 |
| REQ-DATASET-REPLAY-04 | TEST-DATASET-REPLAY-01, TEST-DATASET-REPLAY-02 |
| REQ-DATASET-REPLAY-05 | TEST-DATASET-REPLAY-02 |

---

## Not Tested

- Remote provider-specific replay is tested with mocked HTTP responses only; tests do not perform network downloads.
- Live-bus replay is not tested because active replay is intentionally deferred.
- Network access is not tested; all tests use checked-in fixtures.
