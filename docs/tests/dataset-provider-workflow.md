# Test Spec: Dataset Provider Workflow

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/dataset-provider-workflow.md` |
| Issues | #216, #220, #233, #235, #241, #242, #243, #245 |
| Test module | `tests/test_dataset_provider.py` |

---

## Test Cases

### TEST-DATASET-CATALOG-01: Pivot Auto Dataset Index Metadata

```gherkin
Given the built-in public dataset catalog provider
When the operator inspects `pivot-auto-datasets`
Then the descriptor identifies `https://pivot-auto.org/datasets/` as the source URL
And the descriptor reports mixed per-dataset licensing
And metadata marks the entry as a curated index with notable CAN sources
```

**Fixture:** embedded catalog metadata in `src/canarchy/dataset_catalog.py`

### TEST-DATASET-CATALOG-02: Search Finds Pivot Auto Dataset Index

```gherkin
Given the built-in public dataset catalog provider
When the operator searches for `pivot`
Then the results include `pivot-auto-datasets`
```

**Fixture:** embedded catalog metadata in `src/canarchy/dataset_catalog.py`

### TEST-DATASET-CATALOG-03: Search And Inspect Expose Machine Fields

```gherkin
Given the built-in public dataset catalog provider
When the operator requests dataset search and inspect JSON output
Then each descriptor includes `ref`, `is_replayable`, `is_index`, `default_replay_file`, `download_url_available`, and `source_type`
And replayable datasets identify their default replay file
And curated index datasets identify themselves as indexes
```

**Fixture:** embedded catalog metadata and CLI JSON assertions in `tests/test_dataset_provider.py`

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

### TEST-DATASET-STREAM-06: CLI Streams Candump Source To JSONL

```gherkin
Given a small candump fixture
When the operator runs `canarchy datasets stream --source-format candump --format jsonl`
Then stdout contains JSONL frame events
And the provider ref is preserved in dataset provenance metadata
```

**Fixture:** `tests/fixtures/sample.candump`

### TEST-DATASET-STREAM-07: Help Lists Supported Source Formats

```gherkin
Given the dataset stream command is available
When the operator runs `canarchy datasets stream --help`
Then help text lists both `hcrl-csv` and `candump` source formats
```

**Fixture:** CLI parser help text

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

### TEST-DATASET-REPLAY-03: Closed Replay Stdout Stops Cleanly

```gherkin
Given a mocked remote candump HTTP response
And a replay output handle that raises `BrokenPipeError`
When the operator replays the remote URL
Then replay stops without raising a traceback
And the result reports `stop_reason` as `broken_pipe`
```

**Fixture:** mocked `requests.get` response and broken-pipe writer in `tests/test_dataset_provider.py`

### TEST-DATASET-REPLAY-04: Dry Run Resolves Replay Source Without Streaming

```gherkin
Given the CANdid catalog entry defines default replay metadata
When the operator runs `canarchy datasets replay catalog:candid --dry-run --json`
Then stdout contains a standard JSON result envelope
And the result identifies the resolved replay source, output format, rate, and frame limit
And no remote stream is opened
```

**Fixture:** mocked `requests.get` assertion in `tests/test_dataset_provider.py`

### TEST-DATASET-REPLAY-05: Curated Index Replay Returns Specific Error

```gherkin
Given `catalog:pivot-auto-datasets` is a curated index entry
When the operator requests dataset replay for that ref
Then the command fails with `DATASET_INDEX_NOT_REPLAYABLE`
And no remote stream is opened
```

**Fixture:** embedded catalog metadata and mocked `requests.get` assertion in `tests/test_dataset_provider.py`

### TEST-DATASET-REPLAY-06: Replay Stops At Max Seconds

```gherkin
Given a mocked remote candump HTTP response with frames beyond a one-second capture-time window
When the operator runs `canarchy datasets replay catalog:candid --max-seconds 1.0 --json`
Then stdout contains a standard JSON result envelope
And the result reports only frames inside the window
And the result reports `stop_reason` as `max_seconds`
```

**Fixture:** mocked `requests.get` response in `tests/test_dataset_provider.py`

### TEST-DATASET-REPLAY-07: JSONL Replay Includes Dataset Provenance

```gherkin
Given the CANdid catalog entry defines default replay metadata
When the operator runs `canarchy datasets replay catalog:candid --format jsonl`
Then each emitted frame event includes dataset provenance metadata
And the metadata identifies provider ref, source URL, replay file, default replay file, source format, source type, and frame offset
```

**Fixture:** mocked `requests.get` response in `tests/test_dataset_provider.py`

### TEST-DATASET-REPLAY-08: List Replayable Files

```gherkin
Given the CANdid catalog entry defines replay file metadata
When the operator runs `canarchy datasets replay catalog:candid --list-files --json`
Then stdout contains a standard JSON result envelope
And the result lists replayable files with stable ids, names, sizes, formats, and source URLs
And no remote stream is opened
```

**Fixture:** embedded catalog metadata and mocked `requests.get` assertion in `tests/test_dataset_provider.py`

### TEST-DATASET-REPLAY-09: Replay Selected File

```gherkin
Given the CANdid catalog entry defines multiple replayable CAN logs
When the operator runs `canarchy datasets replay catalog:candid --file 2_indicator_CAN.log --json`
Then replay uses the selected file's source URL
And JSON summary output identifies the selected replay file
```

**Fixture:** embedded catalog metadata and mocked `requests.get` response in `tests/test_dataset_provider.py`

### TEST-DATASET-REPLAY-10: Unknown Replay File Returns Structured Error

```gherkin
Given the CANdid catalog entry defines replay file metadata
When the operator runs `canarchy datasets replay catalog:candid --file missing_CAN.log --json`
Then the command fails with `DATASET_REPLAY_FILE_NOT_FOUND`
And no remote stream is opened
```

**Fixture:** embedded catalog metadata and mocked `requests.get` assertion in `tests/test_dataset_provider.py`

---

## Traceability

| Requirement | Tests |
|-------------|-------|
| REQ-DATASET-CATALOG-01 | TEST-DATASET-CATALOG-01, TEST-DATASET-CATALOG-02 |
| REQ-DATASET-CATALOG-02 | TEST-DATASET-CATALOG-01 |
| REQ-DATASET-CATALOG-03 | TEST-DATASET-CATALOG-01 |
| REQ-DATASET-CATALOG-04 | TEST-DATASET-CATALOG-03 |
| REQ-DATASET-STREAM-01 | TEST-DATASET-STREAM-01, TEST-DATASET-STREAM-02, TEST-DATASET-STREAM-04 |
| REQ-DATASET-STREAM-02 | TEST-DATASET-STREAM-01, TEST-DATASET-STREAM-02, TEST-DATASET-STREAM-06, TEST-DATASET-STREAM-07 |
| REQ-DATASET-STREAM-03 | TEST-DATASET-STREAM-01, TEST-DATASET-STREAM-04 |
| REQ-DATASET-STREAM-04 | TEST-DATASET-STREAM-01, TEST-DATASET-STREAM-04 |
| REQ-DATASET-STREAM-05 | TEST-DATASET-STREAM-03 |
| REQ-DATASET-STREAM-06 | Covered by existing malformed HCRL CSV conversion tests in `tests/test_dataset_provider.py` |
| REQ-DATASET-REPLAY-01 | TEST-DATASET-REPLAY-01 |
| REQ-DATASET-REPLAY-02 | TEST-DATASET-REPLAY-02 |
| REQ-DATASET-REPLAY-03 | TEST-DATASET-REPLAY-01 |
| REQ-DATASET-REPLAY-04 | TEST-DATASET-REPLAY-01, TEST-DATASET-REPLAY-02 |
| REQ-DATASET-REPLAY-05 | TEST-DATASET-REPLAY-02 |
| REQ-DATASET-REPLAY-06 | TEST-DATASET-REPLAY-03 |
| REQ-DATASET-REPLAY-07 | TEST-DATASET-REPLAY-04 |
| REQ-DATASET-REPLAY-08 | TEST-DATASET-REPLAY-05 |
| REQ-DATASET-REPLAY-09 | TEST-DATASET-REPLAY-06 |
| REQ-DATASET-REPLAY-10 | TEST-DATASET-REPLAY-07 |
| REQ-DATASET-REPLAY-11 | TEST-DATASET-REPLAY-08 |
| REQ-DATASET-REPLAY-12 | TEST-DATASET-REPLAY-09 |
| REQ-DATASET-REPLAY-13 | TEST-DATASET-REPLAY-10 |

---

## Not Tested

- Remote provider-specific replay is tested with mocked HTTP responses only; tests do not perform network downloads.
- Live-bus replay is not tested because active replay is intentionally deferred.
- Network access is not tested; all tests use checked-in fixtures.
