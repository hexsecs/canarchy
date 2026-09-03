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


@dataclass(frozen=True, slots=True)
class CaptureStats:
    """Thread-safe snapshot of capture queue activity."""

    received: int = 0
    drained: int = 0
    dropped: int = 0
    queue_depth: int = 0
    high_water_mark: int = 0


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
        self._stats_lock = threading.Lock()
        self._received = 0
        self._drained = 0
        self._dropped = 0
        self._high_water_mark = 0
        self._stop_timeout_reported = False

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

    def stop(self, *, join_timeout: float = 0.25) -> bool:
        """Signal the capture thread and return whether it exited in time."""

        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=join_timeout)
        stopped = thread is None or not thread.is_alive()
        if not stopped and not self._stop_timeout_reported:
            self._errors.put(
                CaptureError(
                    code="CAPTURE_STOP_TIMEOUT",
                    message=f"Capture on '{self.interface}' did not stop within {join_timeout:g}s.",
                    hint="Wait for the backend to close before starting another capture.",
                )
            )
            self._stop_timeout_reported = True
        return stopped

    @property
    def running(self) -> bool:
        return self._thread is not None and not self._finished.is_set()

    @property
    def stats(self) -> CaptureStats:
        """Return an immutable snapshot of producer and consumer counts."""

        with self._stats_lock:
            return CaptureStats(
                received=self._received,
                drained=self._drained,
                dropped=self._dropped,
                queue_depth=self._events.qsize(),
                high_water_mark=self._high_water_mark,
            )

    # -- consumption --------------------------------------------------------

    def drain(self, max_items: int = 256) -> list[dict[str, object]]:
        """Return up to *max_items* buffered events without blocking."""

        drained: list[dict[str, object]] = []
        with self._stats_lock:
            for _ in range(max_items):
                try:
                    drained.append(self._events.get_nowait())
                except queue.Empty:
                    break
            if drained:
                self._drained += len(drained)
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
            for event in self._transport.capture_stream_events(
                self.interface, stop_event=self._stop
            ):
                if self._stop.is_set():
                    break
                with self._stats_lock:
                    self._received += 1
                    # Never block the producer on a full UI queue; drop the
                    # oldest buffered event so live capture keeps flowing.
                    try:
                        self._events.put_nowait(event)
                    except queue.Full:
                        try:
                            self._events.get_nowait()
                            self._dropped += 1
                        except queue.Empty:
                            pass
                        self._events.put_nowait(event)
                    self._high_water_mark = max(self._high_water_mark, self._events.qsize())
        except TransportError as exc:
            self._errors.put(CaptureError(code=exc.code, message=exc.message, hint=exc.hint))
        except Exception as exc:
            self._errors.put(
                CaptureError(
                    code="CAPTURE_FAILED",
                    message=f"Unexpected capture failure: {exc}",
                    hint="Check the transport configuration and retry the capture.",
                )
            )
        finally:
            self._finished.set()
