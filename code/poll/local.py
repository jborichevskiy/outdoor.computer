"""Local checks: internet reachability + derived status (online/degraded/offline).

Pings a known reliable host (1.1.1.1 by default) and classifies overall state
based on its own ping success + the most recent slate/starlink samples.

Status rules (intentionally dumb):
- offline:   no successful slate or starlink poll in the last 30s.
- degraded:  online, but ping latency >200ms or starlink obstruction >0.05.
- online:    everything reachable and fast.

Writes its result to samples as source='derived', metric='status'.
Logs an event on transition.
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import insert_sample, latest_sample, log_event  # noqa: E402
from poll._shared import run_forever  # noqa: E402

INTERVAL_S = 10
PING_HOST = "1.1.1.1"
STALE_S = 30
DEGRADED_LATENCY_MS = 200
DEGRADED_OBSTRUCTION = 0.05

_last_status: str | None = None


def _ping_ms(host: str) -> float | None:
    """Return RTT in ms, or None if ping failed."""
    try:
        out = subprocess.run(
            ["ping", "-c", "1", "-W", "2", host],
            check=True, capture_output=True, text=True, timeout=4,
        ).stdout
        # Line like: "time=12.3 ms"
        for token in out.split():
            if token.startswith("time="):
                return float(token.removeprefix("time="))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return None


def _fresh(conn, source: str, metric: str) -> bool:
    row = latest_sample(conn, source, metric)
    if not row:
        return False
    ts, *_ = row
    return (time.time() - ts) < STALE_S


def poll(conn) -> None:
    global _last_status
    ts = int(time.time())

    rtt = _ping_ms(PING_HOST)
    if rtt is not None:
        insert_sample(conn, "local", "ping_ms", value_num=rtt, ts=ts)
    insert_sample(conn, "local", "ping_ok", value_num=1.0 if rtt is not None else 0.0, ts=ts)

    # Reachability from upstream pollers
    slate_ok    = _fresh(conn, "slate",    "reachable")
    starlink_ok = _fresh(conn, "starlink", "reachable")

    obstruction_row = latest_sample(conn, "starlink", "obstruction")
    obstruction = obstruction_row[1] if obstruction_row else None

    if not (slate_ok or starlink_ok) or rtt is None:
        status = "offline"
    elif (rtt > DEGRADED_LATENCY_MS) or (obstruction is not None and obstruction > DEGRADED_OBSTRUCTION):
        status = "degraded"
    else:
        status = "online"

    insert_sample(conn, "derived", "status", value_text=status, ts=ts)

    if status != _last_status:
        log_event(conn, "status_change", f"{_last_status} -> {status}")
        _last_status = status


if __name__ == "__main__":
    run_forever("local", interval_s=INTERVAL_S, fn=poll)
