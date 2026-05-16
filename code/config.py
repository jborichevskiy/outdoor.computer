"""Config loader. Reads .env from the repo root.

Anything secret or environment-specific goes in .env (not committed).
See .env.example for the full list.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root is parent of `code/`. Load .env from there.
REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")


def _env(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(key, default)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val  # type: ignore[return-value]


# Database
DB_PATH = Path(_env("OUTDOOR_DB_PATH", str(Path.home() / "outdoor" / "data.db")))

# Slate router (SNMP)
SLATE_HOST      = _env("SLATE_HOST", "192.168.8.1")
SLATE_COMMUNITY = _env("SLATE_COMMUNITY", "public")
SLATE_WAN_IFACE = _env("SLATE_WAN_IFACE", "1")  # SNMP ifIndex for the WAN interface

# Starlink dish
STARLINK_ADDR = _env("STARLINK_ADDR", "192.168.100.1:9200")

# Weather (Open-Meteo)
WEATHER_LAT = float(_env("WEATHER_LAT", "40.0150"))  # Boulder, CO default
WEATHER_LON = float(_env("WEATHER_LON", "-105.2705"))

# Web server
WEB_HOST = _env("WEB_HOST", "0.0.0.0")
WEB_PORT = int(_env("WEB_PORT", "8080"))

# Public hostname the ESP32 uses to reach the Pi.
# `outdoor-pi.local` works via mDNS on most LANs.
WEB_PUBLIC_HOST = _env("WEB_PUBLIC_HOST", "outdoor-pi.local")
