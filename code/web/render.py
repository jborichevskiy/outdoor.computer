"""Render the e-ink frame as a 1-bit BMP.

Output format matches what the TRMNL firmware expects:
- 800×480
- 1-bit (mode='1' in PIL)
- BMP format (PIL writes bottom-up rows and 4-byte padding automatically)
- Roughly 48KB on disk

v0 renders a hello-world layout: title, current status, latest readings, timestamp.
The real layout work happens in v1 — keep this file fast to iterate on.
"""

import io
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import connect, latest_sample  # noqa: E402

WIDTH, HEIGHT = 800, 480
BLACK, WHITE = 0, 1  # mode='1' has 0=black, 1=white

# Try to find a reasonable bitmap font on the Pi. Pi OS ships DejaVu by default.
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial.ttf",  # fallback for local dev on macOS
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _fmt_value(row) -> str:
    if not row:
        return "—"
    _ts, num, text = row
    if text is not None:
        return text
    if num is not None:
        return f"{num:.0f}" if abs(num) >= 100 else f"{num:.2f}"
    return "—"


def render_bmp() -> bytes:
    """Return a 1-bit BMP as bytes, freshly built from current SQLite state."""
    img = Image.new("1", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    title_font   = _font(48)
    section_font = _font(28)
    body_font    = _font(22)
    small_font   = _font(16)

    # Title
    draw.text((20, 20), "outdoor.computer", font=title_font, fill=BLACK)
    draw.line([(20, 80), (WIDTH - 20, 80)], fill=BLACK, width=2)

    # Status
    conn = connect()
    status = _fmt_value(latest_sample(conn, "derived", "status"))
    draw.text((20, 100), f"status: {status.upper()}", font=section_font, fill=BLACK)

    # Quick readings (left column)
    y = 160
    rows = [
        ("ping (ms)",     latest_sample(conn, "local",    "ping_ms")),
        ("slate in",      latest_sample(conn, "slate",    "in_octets")),
        ("slate out",     latest_sample(conn, "slate",    "out_octets")),
        ("starlink lat",  latest_sample(conn, "starlink", "latency_ms")),
        ("obstruction",   latest_sample(conn, "starlink", "obstruction")),
    ]
    for label, row in rows:
        draw.text((20, y), f"{label:18s} {_fmt_value(row)}", font=body_font, fill=BLACK)
        y += 32

    # Weather (right column)
    y = 160
    weather_rows = [
        ("temp (°F)",      latest_sample(conn, "weather", "temp_f")),
        ("humidity (%)",   latest_sample(conn, "weather", "humidity_pct")),
        ("wind (mph)",     latest_sample(conn, "weather", "wind_mph")),
    ]
    for label, row in weather_rows:
        draw.text((WIDTH // 2, y), f"{label:18s} {_fmt_value(row)}", font=body_font, fill=BLACK)
        y += 32

    # Footer: timestamp
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    draw.text((20, HEIGHT - 30), f"rendered {stamp}", font=small_font, fill=BLACK)

    conn.close()

    buf = io.BytesIO()
    img.save(buf, format="BMP")
    return buf.getvalue()
