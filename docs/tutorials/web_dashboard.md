# Launch the Web Dashboard

`canarchy web serve` streams a capture through a small read-only browser
dashboard: live frames, bus status, decoded signals, J1939 PGN/source-address
activity, and recent UDS transactions. The CLI stays the contract — the web
layer renders the same JSONL envelope events every other command emits.

No extra dependencies are needed: the server is standard-library HTTP +
WebSocket and the page is a single bundled HTML file.

## 1. Serve a capture

```bash
canarchy web serve --file tests/fixtures/j1939_heavy_vehicle.candump --json
```

The startup envelope reports the URL and confirms the read-only surface:

```json
{
  "command": "web serve",
  "data": {
    "url": "http://127.0.0.1:8474/",
    "read_only": true,
    "event_count": 12,
    "...": "..."
  },
  "ok": true
}
```

Open `http://127.0.0.1:8474/` in a browser. The frame pane fills as the
capture replays at recorded speed; the J1939 pane aggregates PGN activity
with bundled labels and source-address names.

## 2. Add decoded signals

Pass a database (path or provider ref) to populate the decoded-signals pane:

```bash
canarchy web serve --file drive.candump --dbc tests/fixtures/j1939_sample.dbc
```

## 3. Useful knobs

```bash
# replay faster, loop forever, bind elsewhere
canarchy web serve --file drive.candump --rate 10 --loop --bind 127.0.0.1:9000

# bound a huge capture before streaming
canarchy web serve --file long_haul.candump --max-frames 50000
```

* `--rate` scales the timestamp pacing (`--rate 0` streams as fast as possible;
  gaps are capped at 1 s either way).
* `--loop` restarts the stream when the capture ends; otherwise the dashboard
  receives a `STREAM_COMPLETE` alert and the socket closes.
* `--bind 127.0.0.1:0` picks an ephemeral port; the envelope reports it.

## 4. What the server will not do

The dashboard is read-only by design: there are no transmit endpoints, and
every non-GET request returns HTTP 405 with a `WEB_READ_ONLY` error. Active
workflows (`send`, `fuzz`, `replay` to a bus) stay on the CLI behind the
active-transmit safety model. The default bind is loopback; if you expose the
port beyond localhost, you own the transport security.

Press `Ctrl+C` to stop the server.

## See also

* [Design spec](../design/web-serve.md) and [test spec](../tests/web-serve.md)
* [J1939 Heavy Vehicle Analysis](j1939_heavy_vehicle.md) for the CLI-side
  triage of the same capture
