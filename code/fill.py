#!/usr/bin/env python3
"""
fill.py — fills the RLCD one pixel at a time at ~60 px/sec, then unfills.

Uses the PATCH protocol: [0xAA][0xBB][index 4B big-endian][value 1B]
The ESP32 updates one byte of its framebuffer and redraws the full frame.
SPI write (15KB @ 10MHz) takes ~12ms, fitting within the 16.7ms/frame budget.
"""

import struct
import time
import glob
import serial

WIDTH  = 400
HEIGHT = 300
FRAME_BYTES = WIDTH * HEIGHT // 8  # 15000
TARGET_FPS  = 60

# ─── pixel → framebuffer byte ────────────────────────────────────────────────

def pixel_addr(x: int, y: int) -> tuple[int, int]:
    """Return (byte_index, bitmask) for pixel (x, y) in ST7305 landscape packing."""
    inv_y   = HEIGHT - 1 - y
    index   = (x >> 1) * (HEIGHT >> 2) + (inv_y >> 2)
    bit     = 7 - ((inv_y & 3) << 1 | (x & 1))
    return index, 1 << bit

# ─── serial helpers ──────────────────────────────────────────────────────────

def find_port() -> str:
    for pat in ("/dev/cu.usbmodem*", "/dev/cu.usbserial*"):
        m = glob.glob(pat)
        if m:
            return sorted(m)[0]
    return "/dev/cu.usbmodem1101"

def open_serial(port: str) -> serial.Serial:
    ser = serial.Serial(port, 921600, timeout=2, dsrdtr=False, rtscts=False)
    ser.reset_input_buffer()
    time.sleep(0.1)
    return ser

def send_patch(ser: serial.Serial, index: int, value: int):
    packet = b'\xAA\xBB' + struct.pack('>I', index) + bytes([value])
    ser.write(packet)
    ack = ser.read(1)
    if ack != b'\x06':
        reason_byte = ser.read(1)
        code = reason_byte[0] if reason_byte else 0
        raise RuntimeError(f"Patch NAK (code {code:#x}) at index {index}")

def clear_display(ser: serial.Serial):
    """Send a full black frame to reset the display state."""
    from display import _frame_packet
    buf = bytes(FRAME_BYTES)  # all zeros = all black
    packet = _frame_packet(buf)
    ser.write(packet)
    ack = ser.read(2)  # ACK only, or NAK+reason
    if ack[:1] != b'\x06':
        raise RuntimeError(f"Clear failed: {ack!r}")

# ─── fill animation ──────────────────────────────────────────────────────────

def run(port: str):
    buf = bytearray(FRAME_BYTES)  # local mirror of ESP32 framebuffer, starts black
    frame_time = 1.0 / TARGET_FPS
    total = WIDTH * HEIGHT

    print(f"Connecting to {port}...")
    with open_serial(port) as ser:
        print("Clearing display to black...")
        clear_display(ser)
        buf[:] = b'\x00' * FRAME_BYTES

        print(f"Filling {total:,} pixels at {TARGET_FPS} px/sec "
              f"({total / TARGET_FPS:.0f}s to complete)...")

        for phase, label, fill_bit in [(1, "filling", True), (2, "unfilling", False)]:
            print(f"\nPhase {phase}: {label}...")
            t_phase = time.monotonic()

            for y in range(HEIGHT):
                for x in range(WIDTH):
                    t0 = time.monotonic()

                    idx, mask = pixel_addr(x, y)
                    old = buf[idx]
                    if fill_bit:
                        buf[idx] |= mask   # set bit = white
                    else:
                        buf[idx] &= ~mask  # clear bit = black

                    if buf[idx] != old:
                        send_patch(ser, idx, buf[idx])

                    # pace to TARGET_FPS
                    elapsed = time.monotonic() - t0
                    remaining = frame_time - elapsed
                    if remaining > 0:
                        time.sleep(remaining)

            duration = time.monotonic() - t_phase
            actual_fps = total / duration
            print(f"  Done in {duration:.1f}s ({actual_fps:.1f} px/sec actual)")

        print("\nAll done.")

if __name__ == "__main__":
    import sys
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    run(port)
