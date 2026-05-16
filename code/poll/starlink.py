"""Poll the Starlink dish for latency, obstruction, uptime, throughput.

The dish speaks gRPC on 192.168.100.1:9200. Easiest path is the community
library `starlink-grpc-tools` (sparky8512), which wraps the gRPC calls into
Python functions returning dicts.

Install:
    pip install starlink-grpc-tools

If you don't have the dish reachable during development, the poller writes
`reachable=0` rows so the rest of the system can keep working.

TODO: confirm starlink-grpc-tools is installed and uncomment the real path.
For now this is a stub that writes 'reachable=0' so v0 still runs end-to-end.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import insert_sample  # noqa: E402
from poll._shared import run_forever  # noqa: E402

INTERVAL_S = 10


def poll(conn) -> None:
    ts = int(time.time())

    # --- Real implementation (uncomment after `pip install starlink-grpc-tools`) ---
    # from starlink_grpc import status_data, ChannelContext
    # try:
    #     status, *_ = status_data(context=ChannelContext(target=STARLINK_ADDR))
    #     insert_sample(conn, "starlink", "latency_ms",     value_num=status["pop_ping_latency_ms"], ts=ts)
    #     insert_sample(conn, "starlink", "drop_rate",      value_num=status["pop_ping_drop_rate"], ts=ts)
    #     insert_sample(conn, "starlink", "downlink_bps",   value_num=status["downlink_throughput_bps"], ts=ts)
    #     insert_sample(conn, "starlink", "uplink_bps",     value_num=status["uplink_throughput_bps"], ts=ts)
    #     insert_sample(conn, "starlink", "obstruction",    value_num=status["fraction_obstructed"], ts=ts)
    #     insert_sample(conn, "starlink", "uptime_s",       value_num=status["uptime"], ts=ts)
    #     insert_sample(conn, "starlink", "state",          value_text=status["state"], ts=ts)
    #     insert_sample(conn, "starlink", "reachable",      value_num=1.0, ts=ts)
    # except Exception:
    #     insert_sample(conn, "starlink", "reachable", value_num=0.0, ts=ts)
    #     raise

    # --- Stub (v0 placeholder) ---
    insert_sample(conn, "starlink", "reachable", value_num=0.0, ts=ts)


if __name__ == "__main__":
    run_forever("starlink", interval_s=INTERVAL_S, fn=poll)
