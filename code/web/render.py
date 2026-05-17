"""Render the e-ink frame as a 1-bit BMP.

Output format matches what the TRMNL firmware expects:
- 800×480
- 1-bit (mode='1' in PIL)
- BMP format (PIL writes bottom-up rows and 4-byte padding automatically)
- Roughly 48KB on disk
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

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial.ttf",
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


def _hline(draw, y, x0=20, x1=WIDTH - 20, width=2):
    draw.line([(x0, y), (x1, y)], fill=BLACK, width=width)


def render_bmp() -> bytes:
    """Return a 1-bit BMP as bytes, freshly built from current SQLite state."""
    img = Image.new("1", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    title_font   = _font(52)
    section_font = _font(30)
    label_font   = _font(25)
    hero_font    = _font(88)
    small_font   = _font(17)

    MID = 400

    # ── Title ────────────────────────────────────────────────────────────────
    draw.text((20, 16), "OUTDOOR.COMPUTER", font=title_font, fill=BLACK)
    _hline(draw, 80)

    # ── Status ───────────────────────────────────────────────────────────────
    conn = connect()
    status = _fmt_value(latest_sample(conn, "derived", "status"))
    draw.text((20, 90), f"STATUS: {status.upper()}", font=section_font, fill=BLACK)
    _hline(draw, 136)

    # ── Section headers ───────────────────────────────────────────────────────
    draw.text((20, 146), "NETWORK", font=section_font, fill=BLACK)
    draw.text((MID + 20, 146), "WEATHER", font=section_font, fill=BLACK)
    _hline(draw, 188)

    # vertical divider between columns
    draw.line([(MID, 136), (MID, HEIGHT - 44)], fill=BLACK, width=1)

    # ── Network column ────────────────────────────────────────────────────────
    net_rows = [
        ("PING",      latest_sample(conn, "local",    "ping_ms"),     "ms"),
        ("SLATE IN",  latest_sample(conn, "slate",    "in_octets"),   ""),
        ("SLATE OUT", latest_sample(conn, "slate",    "out_octets"),  ""),
        ("LATENCY",   latest_sample(conn, "starlink", "latency_ms"),  "ms"),
        ("OBSTR",     latest_sample(conn, "starlink", "obstruction"), ""),
    ]
    y = 202
    for label, row, unit in net_rows:
        val = _fmt_value(row)
        if unit and val != "—":
            val = f"{val} {unit}"
        draw.text((20, y), label, font=label_font, fill=BLACK)
        draw.text((210, y), val, font=label_font, fill=BLACK)
        y += 38

    # ── Weather column ────────────────────────────────────────────────────────
    temp_raw = latest_sample(conn, "weather", "temp_f")
    if temp_raw and temp_raw[1] is not None:
        temp_display = f"{temp_raw[1]:.0f}°"
    else:
        temp_display = "—°"
    draw.text((MID + 20, 192), temp_display, font=hero_font, fill=BLACK)

    y = 306
    wx_rows = [
        ("HUMIDITY", latest_sample(conn, "weather", "humidity_pct"), "%"),
        ("WIND",     latest_sample(conn, "weather", "wind_mph"),     "mph"),
    ]
    for label, row, unit in wx_rows:
        val = _fmt_value(row)
        if unit and val != "—":
            val = f"{val} {unit}"
        draw.text((MID + 20, y), label, font=label_font, fill=BLACK)
        draw.text((MID + 200, y), val, font=label_font, fill=BLACK)
        y += 38

    # ── Footer ────────────────────────────────────────────────────────────────
    _hline(draw, HEIGHT - 44)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    draw.text((20, HEIGHT - 36), f"RENDERED {stamp}", font=small_font, fill=BLACK)

    conn.close()

    buf = io.BytesIO()
    img.save(buf, format="BMP")
    return buf.getvalue()
