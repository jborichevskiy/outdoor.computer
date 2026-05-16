"""Shared loop helper for pollers.

A poller is a script that runs forever, doing one poll() call every N seconds.
This wrapper handles the loop, exception catching, and event logging so the
poll() function can focus on the actual data fetch.

Usage:

    from poll._shared import run_forever
    from db import connect, insert_sample

    def poll(conn):
        insert_sample(conn, "myname", "mymetric", value_num=42)

    run_forever("myname", interval_s=10, fn=poll)
"""

import sys
import time
import traceback
from typing import Callable

# Make `code/` importable from within `code/poll/`
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from db import connect, log_event  # noqa: E402


def run_forever(
    name: str,
    interval_s: float,
    fn: Callable,
) -> None:
    """Run `fn(conn)` every interval_s seconds. Never exits.

    Errors are logged to `events` and stderr; the loop continues.
    """
    conn = connect()
    log_event(conn, "startup", f"poller={name}")
    print(f"[{name}] starting, interval={interval_s}s", flush=True)

    while True:
        started = time.time()
        try:
            fn(conn)
        except Exception as e:
            tb = traceback.format_exc(limit=2)
            log_event(conn, "poller_error", f"{name}: {e}")
            print(f"[{name}] error: {e}\n{tb}", file=sys.stderr, flush=True)

        # Sleep the remainder of the interval so cadence stays steady even if
        # the poll itself took a while.
        elapsed = time.time() - started
        time.sleep(max(0, interval_s - elapsed))
