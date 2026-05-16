"""Smoke tests for outdoor.computer.

Runs each piece of the stack independently and prints PASS/FAIL.
Use before `./start.sh` on a fresh Pi to catch misconfig fast.

From the repo root:
    cd code && python tools/smoke.py

Exits non-zero if any check failed.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

# Make `code/` importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    DB_PATH,
    SLATE_COMMUNITY,
    SLATE_HOST,
    SLATE_WAN_IFACE,
    STARLINK_ADDR,
    WEATHER_LAT,
    WEATHER_LON,
)
from db import connect, insert_sample, latest_sample  # noqa: E402


def check_db() -> tuple[bool, str]:
    try:
        conn = connect()
        ts = int(time.time())
        insert_sample(conn, "_smoke", "ok", value_num=1.0, ts=ts)
        row = latest_sample(conn, "_smoke", "ok")
        conn.close()
        if row and row[0] == ts:
            return True, f"wrote + read back from {DB_PATH}"
        return False, f"insert succeeded but read-back failed at {DB_PATH}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_snmpget() -> tuple[bool, str]:
    try:
        out = subprocess.run(
            [
                "snmpget", "-v2c", "-c", SLATE_COMMUNITY, "-Oqv",
                "-t", "2", "-r", "1",
                SLATE_HOST, f"IF-MIB::ifInOctets.{SLATE_WAN_IFACE}",
            ],
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return True, f"slate {SLATE_HOST} ifInOctets.{SLATE_WAN_IFACE} = {out}"
    except FileNotFoundError:
        return False, "`snmpget` not installed (sudo apt install snmp)"
    except subprocess.TimeoutExpired:
        return False, f"{SLATE_HOST} timed out (check SLATE_HOST + SNMP enabled on the Slate)"
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or "").strip().splitlines()[-1:] or [""]
        return False, f"snmpget failed: {msg[0]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_starlink_tcp() -> tuple[bool, str]:
    host, _, port = STARLINK_ADDR.partition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=2):
            return True, f"{STARLINK_ADDR} reachable (gRPC port open)"
    except OSError as e:
        return False, f"{STARLINK_ADDR}: {e}"


def check_weather() -> tuple[bool, str]:
    try:
        import requests
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
            "&current=temperature_2m&temperature_unit=fahrenheit"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        temp = r.json()["current"]["temperature_2m"]
        return True, f"open-meteo OK, temp={temp}°F at ({WEATHER_LAT},{WEATHER_LON})"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_ping() -> tuple[bool, str]:
    try:
        subprocess.run(
            ["ping", "-c", "1", "-W", "2", "1.1.1.1"],
            check=True, capture_output=True, timeout=4,
        )
        return True, "1.1.1.1 reachable"
    except subprocess.CalledProcessError:
        return False, "ping returned non-zero (no internet?)"
    except subprocess.TimeoutExpired:
        return False, "ping timed out"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_render() -> tuple[bool, str]:
    try:
        from web.render import render_bmp
        data = render_bmp()
        if not data or data[:2] != b"BM":
            return False, "render produced non-BMP bytes"
        out = Path("/tmp/outdoor-smoke.bmp")
        out.write_bytes(data)
        return True, f"{len(data)} bytes, saved to {out} (scp it back to eyeball)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_webapp_imports() -> tuple[bool, str]:
    try:
        from web import app as _app  # noqa: F401
        return True, "FastAPI app imports cleanly"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


CHECKS = [
    ("db",       check_db),
    ("snmpget",  check_snmpget),
    ("starlink", check_starlink_tcp),
    ("weather",  check_weather),
    ("ping",     check_ping),
    ("render",   check_render),
    ("webapp",   check_webapp_imports),
]


def main() -> None:
    print(f"smoke test — DB_PATH={DB_PATH}\n")
    results = []
    for name, fn in CHECKS:
        ok, detail = fn()
        results.append((name, ok, detail))
        tag = "PASS" if ok else "FAIL"
        print(f"  [{tag}] {name:10s} {detail}")
    print()
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
