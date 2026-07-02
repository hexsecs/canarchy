"""Background live-capture consumer for the full-screen TUI.

`CaptureSession` runs `LocalTransport.capture_stream_events` on a daemon
thread and pushes each canonical event dict onto a queue the UI drains.
It mirrors the transport gateway's thread+queue pattern rather than
inventing a new streaming boundary: the engine already exposes the live
generator, so this module only bridges it into a consumer the Textual app
can poll from its own event loop.

The session owns no protocol logic — it forwards whatever the shared
capture stream yields — keeping the TUI a view over the engine.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from canarchy.transport import LocalTransport, TransportError


@dataclass(frozen=True, slots=True)
class CaptureError:
    """A structured transport error surfaced from the capture thread."""

    code: str
    message: str
    hint: str


class CaptureSession:
    """Own a daemon capture thread feeding events into a queue.

    Usage from the UI: construct with an interface, `start()`, then
    repeatedly `drain(max_items)` from the render loop, and `stop()` when
    done. `errors()` returns any transport error that ended the stream.
    """

    def __init__(
        self,
        interface: str,
        *,
        transport: LocalTransport | None = None,
        maxsize: int = 10000,
    ) -> None:
        self.interface = interface
        self._transport = transport or LocalTransport()
        self._events: queue.Queue[dict[str, object]] = queue.Queue(maxsize=maxsize)
        self._errors: queue.Queue[CaptureError] = queue.Queue()
        self._stop = threading.Event()
        self._finished = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Launch the daemon capture thread (idempotent per session)."""

        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name=f"canarchy-capture-{self.interface}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, join_timeout: float = 0.2) -> None:
        """Signal the capture thread to stop and best-effort join it.

        The underlying `bus.recv()` may block between frames, so the
        thread is a daemon and we do not block the UI waiting on it — a
        short join is attempted and any lingering thread dies with the
        process.
        """

        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=join_timeout)

    @property
    def running(self) -> bool:
        return self._thread is not None and not self._finished.is_set()

    # -- consumption --------------------------------------------------------

    def drain(self, max_items: int = 256) -> list[dict[str, object]]:
        """Return up to *max_items* buffered events without blocking."""

        drained: list[dict[str, object]] = []
        for _ in range(max_items):
            try:
                drained.append(self._events.get_nowait())
            except queue.Empty:
                break
        return drained

    def errors(self) -> list[CaptureError]:
        """Return and clear any transport errors raised by the stream."""

        found: list[CaptureError] = []
        while True:
            try:
                found.append(self._errors.get_nowait())
            except queue.Empty:
                break
        return found

    # -- thread body --------------------------------------------------------

    def _run(self) -> None:
        try:
            for event in self._transport.capture_stream_events(self.interface):
                if self._stop.is_set():
                    break
                # Never block the producer on a full UI queue; drop the
                # oldest buffered event so live capture keeps flowing.
                try:
                    self._events.put_nowait(event)
                except queue.Full:
                    try:
                        self._events.get_nowait()
                    except queue.Empty:
                        pass
                    self._events.put_nowait(event)
        except TransportError as exc:
            self._errors.put(CaptureError(code=exc.code, message=exc.message, hint=exc.hint))
        finally:
            self._finished.set()
