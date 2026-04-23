# J1939 Large-Capture Performance Benchmarks

This document defines performance budgets for J1939 file-backed analysis commands and records benchmark results for reproducibility.

## Benchmark Environment

- **Hardware**: Apple M-series MacBook (darwin arm64)
- **Python**: 3.12
- **Fixture**: `tests/fixtures/j1939_large_benchmark.candump` (10,000 synthetic J1939 frames, ~100 DM1 messages)
- **Generator**: `scripts/generate_benchmark_fixture.py`

## Performance Budgets

| Command | Budget (10k frames) | Observed | Status |
|---------|---------------------|---------|--------|
| `j1939 summary` | < 1.0s | 0.33s | PASS |
| `j1939 decode` | < 2.0s | 0.87s | PASS |
| `j1939 pgn <n>` | < 2.0s | 0.84s | PASS |
| `j1939 spn <n>` | < 2.0s | 0.85s | PASS |
| `j1939 tp` | < 1.0s | 0.35s | PASS |
| `j1939 dm1` | < 5.0s | ~0.4s* | PASS |
| `j1939 summary --max-frames 1000` | < 0.5s | < 0.1s | PASS |

*DM1 performance depends on number of DM1 messages in capture; observed with ~100 DM1 messages in 10k frame capture.

## Benchmark Results

### Methodology
Benchmarks measure end-to-end CLI command execution time using `time` utility:

```bash
time (canarchy j1939 <command> --file tests/fixtures/j1939_large_benchmark.candump --json > /dev/null)
```

### j1939_summary
- **10,000 frames**: 0.33s (well under budget)

### j1939_decode
- **10,000 frames**: 0.87s (under budget)

### j1939_pgn
- **10,000 frames** (PGN 65262): 0.84s (under budget)

### j1939_spn
- **10,000 frames** (SPN 110): 0.85s (under budget)

### j1939_tp
- **10,000 frames**: 0.35s (under budget)

### j1939_dm1
- **10,000 frames** (~100 DM1 messages): ~0.4s (under budget)
- Note: Performance scales with number of DM1 messages; synthetic fixtures without DM1 content will be faster.

## Performance Test Suite

Automated performance tests are in `tests/test_j1939_performance.py`. These tests validate that core J1939 functions meet their budgets:

```bash
uv run pytest tests/test_j1939_performance.py -v
```

## Fixture Generation

```bash
python3 scripts/generate_benchmark_fixture.py --count 10000 --output tests/fixtures/j1939_large_benchmark.candump
```

The generator creates synthetic J1939 frames with:
- 7 common PGNs
- 8 source addresses
- 3 interfaces
- Random DLC (2, 4, or 8 bytes)
- ~1% DM1 messages (PGN 65226) for realistic testing

## Historical Performance Tracking

| Date | Notes |
|------|-------|
| 2026-04-23 | Initial benchmarks; all commands under budget |