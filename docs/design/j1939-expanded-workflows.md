# Design Spec: Expanded J1939 Workflows

## Goal

Expand the J1939 command surface beyond PGN-only views so operators can inspect SPN values, transport-protocol sessions, and DM1 fault traffic using protocol-aware commands.

## Command surface

```text
canarchy j1939 spn <spn> --file <capture>
canarchy j1939 tp <capture>
canarchy j1939 dm1 <capture>
```

## `j1939 spn`

The initial implementation uses a curated SPN decoder map rather than a general J1939 database.

Supported SPNs in the first slice:

* `110` Engine Coolant Temperature from PGN `65262`
* `190` Engine Speed from PGN `61444`

Each observation includes:

* `spn`
* `name`
* `pgn`
* `source_address`
* `destination_address`
* `value`
* `units`
* `raw`
* `timestamp`

If a requested SPN is not in the curated map, the command returns `J1939_SPN_UNSUPPORTED`.

## `j1939 tp`

The first implementation focuses on BAM-based transport sessions:

* TP.CM BAM (`PGN 60416` / `0xEC00`)
* TP.DT data transfer (`PGN 60160` / `0xEB00`)

Each session summary includes:

* `session_type`
* `transfer_pgn`
* `source_address`
* `destination_address`
* `total_bytes`
* `total_packets`
* `packet_count`
* `complete`
* `reassembled_data`

RTS/CTS flow-control details are deferred.

## `j1939 dm1`

DM1 inspection reads both:

* direct DM1 frames on PGN `65226`
* TP-reassembled DM1 payloads whose transported PGN is `65226`

Each message includes:

* `source_address`
* `destination_address`
* `transport` (`direct` or `tp`)
* `lamp_status`
* `active_dtc_count`
* `dtcs`

Each DTC includes:

* `spn`
* `name` when known from the curated SPN map
* `fmi`
* `occurrence_count`
* `conversion_method`

## Deferred

* broader SPN coverage beyond the curated starter map
* RTS/CTS state-machine detail and abort handling for TP
* additional DM messages beyond DM1
