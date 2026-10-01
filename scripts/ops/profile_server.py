#!/usr/bin/env python3

"""Run the FastAPI server with PyInstrument profiling and resource usage stats."""

from __future__ import annotations

import argparse
import os
import re
import resource
import sys
import threading
import time
from pathlib import Path

try:
    import psutil
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    psutil = None


ROOT = Path(__file__).resolve().parents[2]
# Ensure project root is importable so uvicorn can find server.py when invoked from scripts/.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ResourceTracker:
    """Periodically sample the current process tree to aggregate CPU and RSS usage."""

    def __init__(self, interval: float = 0.2) -> None:
        if psutil is None:
            raise RuntimeError("psutil is required for ResourceTracker")
        self.interval = interval
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name="resource-tracker", daemon=True)
        self._last: dict[int, tuple[float, float]] = {}
        self._cpu_user = 0.0
        self._cpu_system = 0.0
        self._peak_rss_bytes = 0
        self._max_cpu_percent = 0.0
        self._last_sample_time: float | None = None
        self._root_pid = os.getpid()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def summary(self) -> dict[str, float]:
        with self._lock:
            return {
                "user_time": self._cpu_user,
                "system_time": self._cpu_system,
                "cpu_time": self._cpu_user + self._cpu_system,
                "peak_rss_mb": self._peak_rss_bytes / (1024.0 * 1024.0),
                "max_cpu_percent": self._max_cpu_percent,
            }

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(self.interval)
        # Final sample after stop to catch last bit of work
        self._sample()

    def _sample(self) -> None:
        try:
            root_proc = psutil.Process(self._root_pid)
        except psutil.Error:
            return

        now = time.perf_counter()
        if self._last_sample_time is None:
            interval = None
        else:
            interval = max(0.0, now - self._last_sample_time)
        self._last_sample_time = now

        with self._lock:
            procs = [root_proc]
            try:
                procs.extend(root_proc.children(recursive=True))
            except psutil.Error:
                pass

            rss_total = 0
            delta_user_sample = 0.0
            delta_system_sample = 0.0
            for proc in procs:
                try:
                    times = proc.cpu_times()
                    mem = proc.memory_info()
                except psutil.Error:
                    continue

                user = getattr(times, "user", 0.0)
                system = getattr(times, "system", 0.0)
                prev = self._last.get(proc.pid)
                include_in_peak = True
                if prev is None:
                    delta_user = user
                    delta_system = system
                    include_in_peak = False
                else:
                    delta_user = max(0.0, user - prev[0])
                    delta_system = max(0.0, system - prev[1])
                self._cpu_user += delta_user
                self._cpu_system += delta_system
                if include_in_peak:
                    delta_user_sample += delta_user
                    delta_system_sample += delta_system
                self._last[proc.pid] = (user, system)

                rss_total += getattr(mem, "rss", 0)

            if rss_total > self._peak_rss_bytes:
                self._peak_rss_bytes = rss_total

            current_pids = {proc.pid for proc in procs}
            for pid in list(self._last):
                if pid not in current_pids:
                    self._last.pop(pid, None)

            if interval and interval > 0.0:
                cpu_count = psutil.cpu_count() or 1
                delta_cpu = delta_user_sample + delta_system_sample
                cpu_percent = (delta_cpu / (interval * cpu_count)) * 100.0 if cpu_count else 0.0
                if cpu_percent > self._max_cpu_percent:
                    self._max_cpu_percent = cpu_percent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start the review server, capture a PyInstrument profile, and print CPU/RAM usage."
        )
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface for uvicorn (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for uvicorn (default: %(default)s)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("data/profile/server-profile.html"),
        help="Where to save the HTML profile report (default: %(default)s)",
    )
    parser.add_argument(
        "--stats-output",
        type=Path,
        default=Path("data/profile/server-stats.html"),
        help="Where to save the resource-usage HTML report (default: %(default)s)",
    )
    return parser.parse_args()


def _gather_resource_deltas(
    start_self: resource.struct_rusage,
    start_children: resource.struct_rusage,
    end_self: resource.struct_rusage,
    end_children: resource.struct_rusage,
) -> dict[str, float]:
    """Compute deltas for CPU time and memory usage (MB)."""
    user_time = (end_self.ru_utime - start_self.ru_utime) + (
        end_children.ru_utime - start_children.ru_utime
    )
    sys_time = (end_self.ru_stime - start_self.ru_stime) + (
        end_children.ru_stime - start_children.ru_stime
    )
    cpu_time = user_time + sys_time
    rss_self = end_self.ru_maxrss
    rss_children = end_children.ru_maxrss
    rss_raw = max(rss_self, rss_children)
    rss_divisor = 1024.0 if sys.platform != "darwin" else 1024.0 * 1024.0
    peak_rss_mb = rss_raw / rss_divisor
    return {
        "user_time": user_time,
        "system_time": sys_time,
        "cpu_time": cpu_time,
        "peak_rss_mb": peak_rss_mb,
        "max_cpu_percent": None,
    }


def main() -> int:
    try:
        from pyinstrument import Profiler
    except ModuleNotFoundError:
        print(
            "PyInstrument is required. Install it with 'pip install pyinstrument' and rerun.",
            file=sys.stderr,
        )
        return 1

    try:
        import uvicorn
    except ModuleNotFoundError:
        print("uvicorn is required. Install project dependencies and rerun.", file=sys.stderr)
        return 1

    args = parse_args()
    profiler = Profiler(async_mode="asyncio")

    tracker: ResourceTracker | None = None
    if psutil is None:
        print(
            "⚠️  Install 'psutil' to include subprocess CPU/RAM usage in the summary and report.",
            file=sys.stderr,
        )
    else:
        tracker = ResourceTracker()
        tracker.start()

    start_wall = time.perf_counter()
    start_self = resource.getrusage(resource.RUSAGE_SELF)
    start_children = resource.getrusage(resource.RUSAGE_CHILDREN)

    # Run uvicorn while profiler is active; we stop and persist results on exit.
    profiler.start()
    try:
        uvicorn.run("server:app", host=args.host, port=args.port, log_level="info")
    finally:
        profiler.stop()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        end_wall = time.perf_counter()
        end_self = resource.getrusage(resource.RUSAGE_SELF)
        end_children = resource.getrusage(resource.RUSAGE_CHILDREN)
        if tracker:
            tracker.stop()
            usage = tracker.summary()
        else:
            usage = _gather_resource_deltas(start_self, start_children, end_self, end_children)

        wall_time = end_wall - start_wall
        cpu_percent = (usage["cpu_time"] / wall_time * 100.0) if wall_time > 0 else 0.0

        summary_html = _build_usage_summary_html(
            wall_time=wall_time,
            cpu_time=usage["cpu_time"],
            user_time=usage["user_time"],
            system_time=usage["system_time"],
            cpu_percent=cpu_percent,
            peak_rss_mb=usage["peak_rss_mb"],
            max_cpu_percent=usage.get("max_cpu_percent"),
            note=(
                "Includes uvicorn and all child processes (run_all.py and scripts 0-5)."
                if tracker
                else "Aggregated from server process; install psutil for recursive tracking."
            ),
        )

        html = profiler.output_html()
        html_with_summary = _inject_summary_html(html, summary_html)
        args.output.write_text(html_with_summary, encoding="utf-8")
        print(f"Profile written to {args.output.resolve()}")

        stats_html = _wrap_summary_as_document(summary_html, title="Server Resource Usage")
        args.stats_output.parent.mkdir(parents=True, exist_ok=True)
        args.stats_output.write_text(stats_html, encoding="utf-8")
        print(f"Resource report written to {args.stats_output.resolve()}")

        print("Resource usage summary:")
        print(f"  Wall time: {wall_time:.2f}s")
        print(
            f"  CPU time: {usage['cpu_time']:.2f}s (user {usage['user_time']:.2f}s, "
            f"system {usage['system_time']:.2f}s)"
        )
        print(f"  Average CPU utilization: {cpu_percent:.1f}%")
        max_cpu = usage.get("max_cpu_percent")
        if max_cpu is not None:
            print(f"  Peak CPU utilization: {max_cpu:.1f}%")
        else:
            print("  Peak CPU utilization: n/a (psutil required)")
        print(f"  Peak RSS: {usage['peak_rss_mb']:.1f} MiB")

    return 0


def _build_usage_summary_html(
    *,
    wall_time: float,
    cpu_time: float,
    user_time: float,
    system_time: float,
    cpu_percent: float,
    peak_rss_mb: float,
    max_cpu_percent: float | None,
    note: str | None = None,
) -> str:
    """Return an HTML snippet with resource usage numbers."""
    note_html = f'<p style="margin:8px 0 0;color:#555;">{note}</p>' if note else ""
    if max_cpu_percent is None:
        peak_cpu_html = "<li>Peak CPU utilisation: n/a (psutil required)</li>"
    else:
        peak_cpu_html = f"<li>Peak CPU utilisation: {max_cpu_percent:.1f}%</li>"
    return (
        '<section class="resource-summary" '
        'style="margin:16px;padding:12px;border:1px solid #ccc;border-radius:6px;'
        'background:#f9f9f9;font-family:system-ui,sans-serif;">'
        '<h2 style="margin-top:0;font-size:1.25rem;">Resource usage summary</h2>'
        '<ul style="margin:0;padding-left:1.25rem;line-height:1.5;">'
        f"<li>Wall time: {wall_time:.2f} s</li>"
        f"<li>CPU time: {cpu_time:.2f} s (user {user_time:.2f} s, system {system_time:.2f} s)</li>"
        f"<li>Average CPU utilisation: {cpu_percent:.1f}%</li>"
        f"{peak_cpu_html}"
        f"<li>Peak RSS: {peak_rss_mb:.1f} MiB</li>"
        "</ul>"
        f"{note_html}"
        "</section>"
    )


def _inject_summary_html(html: str, summary: str) -> str:
    """Insert resource summary snippet right after <body> (or prepend if missing)."""
    match = re.search(r"<body[^>]*>", html, flags=re.IGNORECASE)
    if not match:
        return summary + html
    idx = match.end()
    return html[:idx] + summary + html[idx:]


def _wrap_summary_as_document(summary: str, *, title: str) -> str:
    """Wrap the summary snippet into a standalone HTML document."""
    return (
        "<!doctype html>"
        '<html lang="en">'
        "<head>"
        f'<meta charset="utf-8"><title>{title}</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<style>body{margin:0;padding:24px;font-family:system-ui,sans-serif;background:#fafafa;}"
        "h1{margin-top:0;}a{color:#0b5fff;text-decoration:none;}a:hover{text-decoration:underline;}"
        "</style>"
        "</head>"
        "<body>"
        f"<h1>{title}</h1>"
        f"{summary}"
        "</body>"
        "</html>"
    )


if __name__ == "__main__":
    raise SystemExit(main())
