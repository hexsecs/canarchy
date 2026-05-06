# Security Use Cases With Coding Agents

CANarchy is designed for operators and coding agents working together on CAN security research. These use cases show how an agent can drive repeatable CLI workflows, preserve evidence, and return structured findings without hiding the underlying commands.

## 1. CAN/J1939 Capture Triage

Goal: turn a raw capture into a first-pass security assessment.

Use this when an operator has a candump log from a bench, vehicle, or dataset and wants an agent to identify what is present before deeper analysis. For dataset-backed J1939 work, the agent should start from the dataset catalog, preserve provenance, and avoid substituting non-J1939 data just because it is replayable.

Dataset discovery and provenance commands:

```bash
canarchy datasets search j1939 --json
canarchy datasets inspect catalog:pivot-auto-datasets --json
canarchy datasets inspect catalog:hcrl-j1939-attack --json
canarchy datasets fetch catalog:hcrl-j1939-attack --json
```

The current built-in J1939 catalog entry, `catalog:hcrl-j1939-attack`, represents real SAE J1939 heavy-vehicle attack traffic from HCRL. It is not directly replayable from a public URL in CANarchy because access may require a research-use agreement.

The PIVOT index also links to Colorado State / Jeremy Daily heavy-vehicle datasets that include CAN and J1939 candump logs and challenge data:

* Heavy vehicle CAN and J1939 data: <https://www.engr.colostate.edu/~jdaily/J1939/candata.html>
* Heavy-vehicle cybersecurity challenge data: <https://www.engr.colostate.edu/~jdaily/cyber/challenge_data.html>
* Electronic logging device attack dataset: <https://datadryad.org/dataset/doi:10.5061/dryad.zw3r228jk>

After the operator obtains a dataset file from HCRL, Colorado State, or another linked source, the agent can convert or stream it while preserving dataset provenance where possible. Some linked sources use candump content with non-candump suffixes such as `.txt`; normalize those through `datasets stream --source-format candump` before running file-backed analysis commands:

```bash
canarchy datasets convert hcrl-j1939-attack.csv \
  --source-format hcrl-csv \
  --format candump \
  --output hcrl-j1939-attack.candump \
  --json

canarchy datasets stream CSU090AT.txt \
  --source-format candump \
  --format candump \
  --output CSU090AT.candump \
  --json
```

Triage commands for the converted J1939 capture:

```bash
canarchy capture-info --file hcrl-j1939-attack.candump --json
canarchy stats --file hcrl-j1939-attack.candump --json
canarchy j1939 summary --file hcrl-j1939-attack.candump --json
canarchy j1939 inventory --file hcrl-j1939-attack.candump --json
canarchy j1939 dm1 --file hcrl-j1939-attack.candump --json
```

Agent output should include:

* capture size, duration, interfaces, and unique arbitration IDs
* top CAN IDs or J1939 PGNs and source addresses
* ECU/node inventory where protocol metadata is available
* transport-protocol sessions and completeness
* DM1 diagnostic messages, DTCs, lamp states, and source addresses
* commands run, files analyzed, and any limits such as `--max-frames` or `--seconds`

If no J1939 dataset payload is available locally, the agent should stop after `datasets inspect` / `datasets fetch`, report the access requirement or linked source page, and ask the operator for the downloaded dataset file. It should not use `catalog:candid` for this use case because CANdid is CAN traffic, not J1939.

Colorado State example using `2014_KW_T270_Short_CSU090AT.zip` from the Jeremy Daily heavy vehicle CAN/J1939 page:

```bash
canarchy datasets stream CSU090AT.txt --source-format candump --format candump --output CSU090AT.candump --json
canarchy capture-info --file CSU090AT.candump --json
canarchy stats --file CSU090AT.candump --json
canarchy j1939 summary --file CSU090AT.candump --json
canarchy j1939 inventory --file CSU090AT.candump --json
canarchy j1939 dm1 --file CSU090AT.candump --json
```

Observed result on the downloaded CSU log: 28,595 frames over 79.68 seconds, 104 unique arbitration IDs, 76 unique PGNs, 7 source addresses, 35 complete BAM transport sessions, component identifiers for the cab controller, brake controller, and transmission, and one VIN-like vehicle identification string (`2NKHHM6X2EM406412*`) from source address 0. DM1 was present from source addresses 0, 3, 11, and 49 with 88 messages; CANarchy reported no active DTCs and warned that some DTCs used deprecated SPN conversion modes.

Development smoke-test commands, using the repository fixture only to validate the analysis sequence:

```bash
canarchy j1939 summary --file tests/fixtures/j1939_heavy_vehicle.candump --json
canarchy j1939 inventory --file tests/fixtures/j1939_heavy_vehicle.candump --json
canarchy j1939 dm1 --file tests/fixtures/j1939_heavy_vehicle.candump --json
```

Observed fixture result: 8 J1939 frames, 4 unique PGNs, one source address (`49`, Cab Controller - Primary), one complete BAM transport session, and one DM1 message carrying two active DTCs for SPNs 110 and 190. This fixture result proves the command sequence, but it is not a substitute for the dataset-backed HCRL J1939 capture.

## 2. Dataset-Driven IDS Experimentation

Goal: evaluate public CAN attack datasets safely and reproducibly.

An agent can search dataset catalogs, inspect access notes, plan remote replay without streaming, then run bounded replay or local conversion for IDS experiments.

Representative commands:

```bash
canarchy datasets search intrusion --json
canarchy datasets inspect catalog:candid --json
canarchy datasets replay catalog:candid --list-files --json
canarchy datasets replay catalog:candid --dry-run --max-frames 1000 --json
canarchy datasets replay catalog:candid --file 2_brakes_CAN.log --max-frames 1000 --format jsonl
canarchy re entropy --file sample.candump --json
canarchy re counters --file sample.candump --json
```

Agent output should distinguish replayable datasets from curated indexes, state license/access notes, bound frame streaming where possible, and keep dataset provenance in results.

## 3. DBC-Assisted Signal Reconnaissance

Goal: identify and decode meaningful signals from raw traffic.

An agent can search provider-backed DBC catalogs, inspect likely matches, decode captures, and compare decoded signals with reverse-engineering hints.

Representative commands:

```bash
canarchy dbc search toyota --limit 10 --json
canarchy dbc fetch opendbc:toyota_tnga_k_pt --json
canarchy dbc inspect opendbc:toyota_tnga_k_pt --json
canarchy decode --file trace.candump --dbc opendbc:toyota_tnga_k_pt --json
canarchy re match-dbc trace.candump --json
```

Agent output should call out safety-critical signals such as brake, steering, torque, speed, diagnostic state, checksums, counters, and messages that did not match the chosen DBC.

## 4. Protocol-Aware Incident Report Generation

Goal: convert analysis evidence into a defensible report.

An agent can collect structured outputs across raw CAN, J1939, DBC, UDS, and reverse-engineering helpers, then produce an incident report with commands and artifacts.

Representative commands:

```bash
canarchy capture-info --file incident.candump --json
canarchy stats --file incident.candump --json
canarchy j1939 summary --file incident.candump --json
canarchy j1939 faults --file incident.candump --json
canarchy uds services --json
canarchy re entropy --file incident.candump --json
```

Agent output should include a concise executive summary, protocol findings, suspicious evidence, limitations, reproducibility commands, and follow-up questions for the operator.

## 5. Safe Replay And Regression Testing

Goal: reproduce traffic in a lab while keeping active actions explicit and bounded.

An agent can generate repeatable scripts for replaying known captures, running comparisons, and verifying parser or detection stability across code changes.

Representative commands:

```bash
canarchy replay --file trace.candump --rate 0.5 --json
canarchy datasets replay catalog:candid --dry-run --json
canarchy datasets replay catalog:candid --file 2_brakes_CAN.log --max-frames 100 --rate 10
canarchy j1939 compare before.candump after.candump --json
```

Agent output should clearly separate passive analysis from active transmit/replay, show rate and frame/time limits, and preserve enough metadata for another operator to reproduce the same run.
