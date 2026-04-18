# Test Spec: Expanded J1939 Workflows

## Coverage goals

* `j1939 spn` capture-file requirement
* `j1939 spn` structured value extraction from a supported SPN
* `j1939 tp` BAM session summary and reassembly
* `j1939 dm1` parsing for both direct and TP-reassembled messages
* table output for DM1 remains human-readable

## Test cases

### SPN capture-file requirement

**Action:** run `canarchy j1939 spn 110 --json`.  
**Assert:** exit code `1` and `errors[0].code == "CAPTURE_FILE_REQUIRED"`.

### SPN observation extraction

**Setup:** use a capture fixture containing PGN `65262`.  
**Action:** run `canarchy j1939 spn 110 --file sample.candump --json`.  
**Assert:** one observation is returned with the expected SPN, PGN, source address, decoded value, and units.

### TP BAM session summary

**Setup:** use a fixture containing TP.CM BAM and TP.DT frames for a DM1 payload.  
**Action:** run `canarchy j1939 tp j1939_dm1_tp.candump --json`.  
**Assert:** one complete BAM session is returned with the expected transferred PGN, packet count, and reassembled payload bytes.

### DM1 direct and transported parsing

**Setup:** use a fixture containing one direct DM1 and one TP-reassembled DM1.  
**Action:** run `canarchy j1939 dm1 j1939_dm1_tp.candump --json`.  
**Assert:** both messages are returned; the TP one has two DTCs and the direct one preserves its source address and FMI.

### DM1 table output

**Action:** run `canarchy j1939 dm1 j1939_dm1_tp.candump --table`.  
**Assert:** output includes the command header, message section, transport label, and DTC summaries.

## Fixtures

* existing `sample.candump`
* `j1939_dm1_tp.candump` for TP and DM1 coverage

## What is not tested

* full RTS/CTS transport control flows
* large multi-packet TP sessions beyond the BAM starter path
* broad SPN database coverage beyond the curated starter decoder set
