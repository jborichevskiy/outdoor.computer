#!/usr/bin/env python3
"""
Raspberry Pi → ESP32-S3-RLCD-4.2 display driver

Architecture:
  Pi sends a 300×400 1bpp frame to ESP32 over USB serial (USB-A → USB-C).
  ESP32 firmware receives the frame and writes it to the RLCD via SPI.

  Alternative: use send_frame_wifi() if the ESP32 is running an HTTP server.

Requirements:
  pip install pyserial pillow
"""

import struct
import sys
from PIL import Image, ImageDraw, ImageFont

WIDTH = 400   # landscape (physical panel is 300×400 portrait, rotated via MADCTL)
HEIGHT = 300

# Simple framing protocol: [magic 2B][length 4B][pixels NB][checksum 1B]
FRAME_MAGIC = b'\xAA\x55'


def render_image(img_path: str) -> Image.Image:
    return Image.open(img_path).convert("L").resize((WIDTH, HEIGHT))


def render_text(lines: list[str], font_size: int = 24) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()
    y = 8
    for line in lines:
        draw.text((8, y), line, fill=0, font=font)
        y += font_size + 4
    return img


def image_to_1bpp(img: Image.Image, threshold: int = 128) -> bytes:
    """
    Pack pixels for the ST7305 landscape mode.

    Matches Waveshare RLCD_SetLandscapePixel() exactly:
      inv_y  = (HEIGHT-1) - y
      index  = (x//2) * (HEIGHT//4) + (inv_y//4)
      bit    = 7 - ((inv_y%4)*2 + (x%2))
      1 = white (paper), 0 = black (ink)

    Each byte covers 2 x-positions × 4 y-positions = 8 pixels.
    Total: (WIDTH/2) * (HEIGHT/4) = 200 * 75 = 15000 bytes.
    """
    img = img.convert("L").resize((WIDTH, HEIGHT))
    pixels = img.load()
    buf = bytearray(WIDTH * HEIGHT // 8)  # 15000, initialised to 0 (black)
    H4 = HEIGHT // 4  # 75

    for y in range(HEIGHT):
        inv_y = HEIGHT - 1 - y
        block_y = inv_y >> 2
        local_y = inv_y & 3
        for x in range(WIDTH):
            if pixels[x, y] >= threshold:  # white pixel
                index = (x >> 1) * H4 + block_y
                bit = 7 - ((local_y << 1) | (x & 1))
                buf[index] |= 1 << bit

    return bytes(buf)


def _frame_packet(payload: bytes) -> bytes:
    checksum = sum(payload) & 0xFF
    return FRAME_MAGIC + struct.pack(">I", len(payload)) + payload + bytes([checksum])


def send_frame_serial(frame_bytes: bytes, port: str = "/dev/ttyUSB0", baud: int = 921600):
    import serial
    import time
    packet = _frame_packet(frame_bytes)
    # dsrdtr/rtscts=False prevents pyserial from toggling DTR/RTS on open,
    # which would reset the ESP32 before we can send anything.
    _NAK_REASONS = {
        0x01: "length header timeout",
        0x02: f"wrong length (ESP32 expects {WIDTH * HEIGHT // 8} bytes)",
        0x03: "pixel data timeout (ESP32 stopped receiving mid-frame)",
        0x04: "checksum byte timeout",
        0x05: "checksum mismatch",
    }
    with serial.Serial(port, baud, timeout=5, dsrdtr=False, rtscts=False) as ser:
        ser.reset_input_buffer()
        time.sleep(0.1)  # brief pause in case the board just booted
        ser.write(packet)
        ack = ser.read(1)
        if ack == b'\x06':
            return
        reason_byte = ser.read(1)
        reason = _NAK_REASONS.get(reason_byte[0] if reason_byte else 0, "unknown")
        raise RuntimeError(f"NAK from ESP32: {reason}")


def send_frame_wifi(frame_bytes: bytes, esp32_ip: str, port: int = 8080):
    import socket
    packet = _frame_packet(frame_bytes)
    with socket.create_connection((esp32_ip, port), timeout=5) as sock:
        sock.sendall(packet)
        ack = sock.recv(1)
        if ack != b'\x06':
            raise RuntimeError(f"Expected ACK (0x06), got: {ack!r}")


def find_serial_port() -> str:
    import glob
    # Mac: ESP32-S3 USB CDC shows up as usbmodem; CP210x as usbserial
    for pattern in ("/dev/cu.usbmodem*", "/dev/cu.usbserial*", "/dev/cu.SLAB_USBtoUART*"):
        matches = glob.glob(pattern)
        if matches:
            return sorted(matches)[0]
    return "/dev/cu.usbmodem1101"  # fallback guess


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Send image to ESP32-S3-RLCD display")
    parser.add_argument("--port", default=None, help="Serial port (auto-detected if omitted)")
    parser.add_argument("--ip", help="ESP32 IP address (Wi-Fi mode)")
    parser.add_argument("--image", help="Image file to display")
    parser.add_argument("--text", nargs="+", help="Lines of text to display")
    parser.add_argument("--threshold", type=int, default=128)
    args = parser.parse_args()

    if args.image:
        img = render_image(args.image)
    elif args.text:
        img = render_text(args.text)
    else:
        img = render_text(["outdoor.computer", "no content yet"])

    frame = image_to_1bpp(img, threshold=args.threshold)
    print(f"Frame: {len(frame)} bytes ({WIDTH}x{HEIGHT} @ 1bpp)")

    if args.ip:
        print(f"Sending via Wi-Fi to {args.ip}...")
        send_frame_wifi(frame, args.ip)
    else:
        port = args.port or find_serial_port()
        print(f"Sending via serial to {port}...")
        send_frame_serial(frame, port)

    print("Done.")
