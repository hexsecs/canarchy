"""Signal time-series plotting via matplotlib."""

from __future__ import annotations

try:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
except ImportError:
    plt = None  # type: ignore

try:
    import plotly.graph_objects as go

    _PLOTLY_AVAILABLE = True
except ImportError:
    go = None  # type: ignore
    _PLOTLY_AVAILABLE = False


class PlotDependencyError(Exception):
    def __init__(self, dependency: str) -> None:
        self.dependency = dependency
        super().__init__(f"{dependency} is required for plotting.")


def decode_signal_series(
    capture_file: str,
    dbc_file: str,
    signals: list[str],
    *,
    offset: int = 0,
    max_frames: int | None = None,
    seconds: float | None = None,
) -> dict[str, list[tuple[float, float]]]:
    """Return {signal_name: [(timestamp, value), ...]} for each requested signal."""
    import cantools.database

    from canarchy.transport import LocalTransport

    db = cantools.database.load_file(dbc_file)
    frames = LocalTransport().frames_from_file(
        capture_file,
        offset=offset,
        max_frames=max_frames,
        seconds=seconds,
    )

    series: dict[str, list[tuple[float, float]]] = {s: [] for s in signals}

    for frame in frames:
        try:
            decoded = db.decode_message(frame.arbitration_id, bytes(frame.data))
        except Exception:
            continue

        ts = frame.timestamp if frame.timestamp is not None else 0.0
        for signal_name in signals:
            if signal_name in decoded:
                value = decoded[signal_name]
                try:
                    series[signal_name].append((float(ts), float(value)))
                except (TypeError, ValueError):
                    pass

    return series


def plot_signals(
    series: dict[str, list[tuple[float, float]]],
    *,
    output_path: str,
    output_format: str,
    title: str = "CANarchy Signal Plot",
) -> dict[str, int]:
    """Write the plot to output_path. Returns {"signals_plotted": N, "data_points": M}."""
    signals_plotted = sum(1 for pts in series.values() if pts)
    data_points = sum(len(pts) for pts in series.values())

    if output_format in ("png", "svg"):
        if plt is None:
            raise PlotDependencyError("matplotlib")

        signal_names = list(series.keys())
        n = len(signal_names)
        fig, axes = plt.subplots(n, 1, figsize=(10, 3 * max(n, 1)))
        if n == 1:
            axes = [axes]

        for ax, signal_name in zip(axes, signal_names):
            pts = series[signal_name]
            if pts:
                xs, ys = zip(*pts)
                ax.plot(xs, ys)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel(signal_name)

        fig.suptitle(title)
        plt.tight_layout()
        plt.savefig(output_path, format=output_format)
        plt.close(fig)

    elif output_format == "html":
        if not _PLOTLY_AVAILABLE:
            raise PlotDependencyError("plotly")

        fig = go.Figure()
        for signal_name, pts in series.items():
            if pts:
                xs, ys = zip(*pts)
                fig.add_trace(go.Scatter(x=list(xs), y=list(ys), name=signal_name))
        fig.update_layout(title=title)
        fig.write_html(output_path)

    return {"signals_plotted": signals_plotted, "data_points": data_points}
