"""Poll the GL.iNet Slate via SNMP for WAN throughput and uptime.

Approach: shell out to `snmpget` (from the `snmp` Debian package). Simpler than
adding a Python SNMP lib, and easy to debug by just running snmpget at the CLI.

Install on Pi: `sudo apt install snmp`

Slate config required:
- SNMP enabled (System → Advanced settings → SNMP)
- Community string set, restricted to LAN
- WAN interface SNMP ifIndex usually 1 or 2; check via:
    snmpwalk -v2c -c <community> <slate-ip> IF-MIB::ifDescr

The poller writes raw byte counters; sparklines can be computed by
differencing successive samples in the web/render layer.
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SLATE_COMMUNITY, SLATE_HOST, SLATE_WAN_IFACE  # noqa: E402
from db import insert_sample  # noqa: E402
from poll._shared import run_forever  # noqa: E402

INTERVAL_S = 10


def _snmp_get(oid: str) -> int | None:
    """Run snmpget and return the integer value, or None on error."""
    try:
        out = subprocess.run(
            [
                "snmpget", "-v2c", "-c", SLATE_COMMUNITY, "-Oqv", "-t", "2", "-r", "1",
                SLATE_HOST, oid,
            ],
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        # Counter values come back as bare integers with -Oqv
        return int(out)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return None


def poll(conn) -> None:
    iface = SLATE_WAN_IFACE
    # IF-MIB::ifInOctets / ifOutOctets — total bytes since boot for this interface.
    # 64-bit counters (ifHCInOctets / ifHCOutOctets) are at .1.3.6.1.2.1.31.1.1.1.{6,10}
    # but not all firmwares expose them; 32-bit is safest baseline.
    in_octets  = _snmp_get(f"IF-MIB::ifInOctets.{iface}")
    out_octets = _snmp_get(f"IF-MIB::ifOutOctets.{iface}")
    uptime     = _snmp_get("DISMAN-EVENT-MIB::sysUpTimeInstance")

    ts = int(time.time())
    if in_octets is not None:
        insert_sample(conn, "slate", "in_octets",  value_num=in_octets,  ts=ts)
    if out_octets is not None:
        insert_sample(conn, "slate", "out_octets", value_num=out_octets, ts=ts)
    if uptime is not None:
        # sysUpTimeInstance is in hundredths of seconds
        insert_sample(conn, "slate", "uptime_s",   value_num=uptime / 100.0, ts=ts)

    insert_sample(
        conn, "slate", "reachable",
        value_num=1.0 if in_octets is not None else 0.0, ts=ts,
    )


if __name__ == "__main__":
    run_forever("slate", interval_s=INTERVAL_S, fn=poll)
