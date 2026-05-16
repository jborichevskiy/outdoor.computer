"""FastAPI web app: BYOS endpoint for the ESP32 + bulletin board + dashboard.

Endpoints:
  GET  /                              dashboard view (HTML)
  GET  /api/display                   TRMNL-shape JSON; image_url has fresh timestamp
  GET  /image/display_{ts}.bmp        renders the current frame on demand
  GET  /image/preview.png             same render, PNG, for the dashboard
  GET  /bulletin                      bulletin board (HTML)
  POST /bulletin                      add a message {username, message}

The ESP32 firmware skips downloads if filename matches previous, so
/api/display always emits a fresh timestamp suffix.
"""

import io
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import WEB_HOST, WEB_PORT, WEB_PUBLIC_HOST  # noqa: E402
from db import connect, latest_sample, log_event  # noqa: E402
from web.render import render_bmp  # noqa: E402

app = FastAPI(title="outdoor.computer")


@app.get("/api/setup")
def api_setup(request: Request):
    """Called by the ESP32 on first boot (or whenever SPIFFS has no saved API key).

    Local trust model: we don't validate or track devices. Just hand back a stub
    api_key that the rest of the endpoints also don't check, plus a friendly_id
    derived from the device's MAC for log clarity. The ESP32 saves both to flash
    and uses them on subsequent /api/display calls.

    Logs the setup to the `events` table so you can see when devices first connect.
    """
    device_id = request.headers.get("ID", "unknown")
    ts = int(time.time())

    conn = connect()
    log_event(conn, "device_setup", f"id={device_id}")
    conn.close()

    friendly = device_id.replace(":", "")[-6:].upper() or "OUTDR1"
    return {
        "status":      200,
        "api_key":     "outdoor-computer-local",
        "friendly_id": friendly,
        "image_url":   f"http://{WEB_PUBLIC_HOST}:{WEB_PORT}/image/display_{ts}.bmp",
        "filename":    f"setup_{ts}",
    }


@app.get("/api/display")
def api_display():
    """ESP32 polls this on its refresh cadence. Returns JSON pointing at a
    freshly-timestamped BMP URL (the timestamp is critical — the firmware skips
    download if filename matches previous fetch)."""
    ts = int(time.time())
    return {
        "status":          0,
        "image_url":       f"http://{WEB_PUBLIC_HOST}:{WEB_PORT}/image/display_{ts}.bmp",
        "filename":        f"display_{ts}",
        "refresh_rate":    "900",   # 15 min, matches firmware default
        "update_firmware": False,
        "firmware_url":    None,
        "reset_firmware":  False,
    }


@app.post("/api/log")
def api_log(request: Request):
    """The ESP32 POSTs here when it detects issues with /api/display responses.
    Just acknowledge — we don't parse the payload, but logging the fact that
    something went wrong on the device is useful."""
    conn = connect()
    log_event(conn, "device_log", f"from={request.client.host if request.client else '?'}")
    conn.close()
    return {"status": 200}


@app.get("/image/display_{ts}.bmp")
def image_bmp(ts: int):
    """Render the current frame as 1-bit BMP. The {ts} is just a cache-bust."""
    data = render_bmp()
    return Response(content=data, media_type="image/bmp")


@app.get("/image/preview.png")
def image_preview():
    """Same render but PNG, for the dashboard preview."""
    from PIL import Image
    bmp = render_bmp()
    img = Image.open(io.BytesIO(bmp))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return Response(content=out.getvalue(), media_type="image/png")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    conn = connect()
    status = latest_sample(conn, "derived", "status")
    status_text = status[2] if status and status[2] else "unknown"
    conn.close()

    return f"""<!doctype html>
<html><head><title>outdoor.computer</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; }}
  img {{ max-width: 100%; border: 1px solid #ccc; image-rendering: pixelated; }}
  .status {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-weight: bold; }}
  .online {{ background: #d4f4d4; }}
  .degraded {{ background: #fff3cd; }}
  .offline {{ background: #f4d4d4; }}
  nav a {{ margin-right: 16px; }}
</style></head>
<body>
  <h1>outdoor.computer</h1>
  <p>status: <span class="status {status_text}">{status_text}</span></p>
  <nav><a href="/">dashboard</a><a href="/bulletin">bulletin</a></nav>
  <h2>e-ink preview</h2>
  <img src="/image/preview.png?t={int(time.time())}" alt="e-ink preview">
</body></html>"""


@app.get("/bulletin", response_class=HTMLResponse)
def bulletin_get():
    conn = connect()
    rows = list(conn.execute(
        "SELECT ts, username, message FROM bulletin ORDER BY ts DESC LIMIT 50"
    ))
    conn.close()
    items = "".join(
        f"<li><b>{u}</b> "
        f"<small>({time.strftime('%Y-%m-%d %H:%M', time.localtime(t))})</small>"
        f"<br>{m}</li>"
        for t, u, m in rows
    )
    return f"""<!doctype html>
<html><head><title>bulletin · outdoor.computer</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px; }}
  form {{ margin-bottom: 30px; }}
  input, textarea {{ width: 100%; padding: 8px; margin: 4px 0; box-sizing: border-box; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ border-bottom: 1px solid #eee; padding: 12px 0; }}
</style></head>
<body>
  <h1>bulletin</h1>
  <p><a href="/">← back</a></p>
  <form method="post" action="/bulletin">
    <input name="username" placeholder="your name" required maxlength="40">
    <textarea name="message" placeholder="say something" required maxlength="500" rows="3"></textarea>
    <button type="submit">post</button>
  </form>
  <ul>{items or "<li>no messages yet</li>"}</ul>
</body></html>"""


@app.post("/bulletin")
def bulletin_post(username: str = Form(...), message: str = Form(...)):
    conn = connect()
    conn.execute(
        "INSERT INTO bulletin(ts, username, message) VALUES (?, ?, ?)",
        (int(time.time()), username.strip()[:40], message.strip()[:500]),
    )
    conn.close()
    return Response(status_code=303, headers={"Location": "/bulletin"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)
