"""Poll Open-Meteo for current weather.

Free, no API key, generous rate limit. Default location is Boulder, CO; override
via WEATHER_LAT / WEATHER_LON in .env.

Docs: https://open-meteo.com/en/docs
"""

import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import WEATHER_LAT, WEATHER_LON  # noqa: E402
from db import insert_sample  # noqa: E402
from poll._shared import run_forever  # noqa: E402

INTERVAL_S = 600  # 10 min — weather doesn't change fast


def poll(conn) -> None:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    cur = r.json()["current"]
    ts = int(time.time())

    insert_sample(conn, "weather", "temp_f",         value_num=cur["temperature_2m"], ts=ts)
    insert_sample(conn, "weather", "humidity_pct",   value_num=cur["relative_humidity_2m"], ts=ts)
    insert_sample(conn, "weather", "wind_mph",       value_num=cur["wind_speed_10m"], ts=ts)
    insert_sample(conn, "weather", "code",           value_num=cur["weather_code"], ts=ts)


if __name__ == "__main__":
    run_forever("weather", interval_s=INTERVAL_S, fn=poll)
