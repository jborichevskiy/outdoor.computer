/*
 * rlcd_receiver.ino
 * ESP32-S3-RLCD-4.2 frame receiver
 *
 * Listens for 400x300 1bpp frames over USB serial, writes to ST7305 via SPI.
 * Init sequence and pixel format taken verbatim from Waveshare display_bsp.cpp.
 *
 * Protocol (matches display.py):
 *   [0xAA][0x55][length 4B big-endian][pixels 15000B][checksum 1B]
 *   Responds with 0x06 (ACK) or 0x15 (NAK)
 *
 * Board: ESP32-S3 Dev Module, USB CDC On Boot: Enabled
 * Required: Arduino ESP32 core >= 3.3.0
 *
 * Pin mapping:
 *   RLCD_SCK   -> GPIO 11
 *   RLCD_DIN   -> GPIO 12  (MOSI)
 *   RLCD_CS    -> GPIO 40
 *   RLCD_DS    -> GPIO 5   (data/command)
 *   RLCD_RESET -> GPIO 41
 */

#include <SPI.h>

#define PIN_SCK    11
#define PIN_MOSI   12
#define PIN_CS     40
#define PIN_DS      5
#define PIN_RESET  41

#define DISPLAY_W   400
#define DISPLAY_H   300
#define FRAME_BYTES ((DISPLAY_W * DISPLAY_H) / 8)  // 15000

#define BAUD   921600
#define ACK    0x06
#define NAK    0x15

static uint8_t framebuf[FRAME_BYTES];

// ---------------------------------------------------------------------------
// ST7305 low-level helpers
// ---------------------------------------------------------------------------

static inline void ds_cmd()  { digitalWrite(PIN_DS, LOW); }
static inline void ds_data() { digitalWrite(PIN_DS, HIGH); }
static inline void cs_lo()   { digitalWrite(PIN_CS, LOW); }
static inline void cs_hi()   { digitalWrite(PIN_CS, HIGH); }

static void send_cmd(uint8_t cmd) {
  ds_cmd(); cs_lo();
  SPI.transfer(cmd);
  cs_hi();
}

static void send_data(uint8_t d) {
  ds_data(); cs_lo();
  SPI.transfer(d);
  cs_hi();
}

// ---------------------------------------------------------------------------
// ST7305 init — verbatim from Waveshare display_bsp.cpp RLCD_Init()
// ---------------------------------------------------------------------------

static void rlcd_reset() {
  digitalWrite(PIN_RESET, HIGH); delay(50);
  digitalWrite(PIN_RESET, LOW);  delay(20);
  digitalWrite(PIN_RESET, HIGH); delay(50);
}

static void rlcd_init() {
  rlcd_reset();

  send_cmd(0xD6); send_data(0x17); send_data(0x02);  // NVM Load Control
  send_cmd(0xD1); send_data(0x01);                   // Booster Enable
  send_cmd(0xC0); send_data(0x11); send_data(0x04);  // Gate Voltage Control
  send_cmd(0xC1); send_data(0x69); send_data(0x69); send_data(0x69); send_data(0x69);  // VSHP
  send_cmd(0xC2); send_data(0x19); send_data(0x19); send_data(0x19); send_data(0x19);
  send_cmd(0xC4); send_data(0x4B); send_data(0x4B); send_data(0x4B); send_data(0x4B);
  send_cmd(0xC5); send_data(0x19); send_data(0x19); send_data(0x19); send_data(0x19);
  send_cmd(0xD8); send_data(0x80); send_data(0xE9);
  send_cmd(0xB2); send_data(0x02);
  send_cmd(0xB3); send_data(0xE5); send_data(0xF6); send_data(0x05); send_data(0x46);
                  send_data(0x77); send_data(0x77); send_data(0x77); send_data(0x77);
                  send_data(0x76); send_data(0x45);
  send_cmd(0xB4); send_data(0x05); send_data(0x46); send_data(0x77); send_data(0x77);
                  send_data(0x77); send_data(0x77); send_data(0x76); send_data(0x45);
  send_cmd(0x62); send_data(0x32); send_data(0x03); send_data(0x1F);
  send_cmd(0xB7); send_data(0x13);
  send_cmd(0xB0); send_data(0x64);

  send_cmd(0x11);  // Sleep Out
  delay(200);

  send_cmd(0xC9); send_data(0x00);
  send_cmd(0x36); send_data(0x48);  // MADCTL: landscape
  send_cmd(0x3A); send_data(0x11);  // Pixel format: ST7305 1bpp mode
  send_cmd(0xB9); send_data(0x20);
  send_cmd(0xB8); send_data(0x29);
  send_cmd(0x21);                   // Invert display

  send_cmd(0x2A); send_data(0x12); send_data(0x2A);  // Column address window
  send_cmd(0x2B); send_data(0x00); send_data(0xC7);  // Row address window

  send_cmd(0x35); send_data(0x00);  // Tearing effect line on
  send_cmd(0xD0); send_data(0xFF);
  send_cmd(0x38);                   // Exit Idle Mode
  send_cmd(0x29);                   // Display ON

  // Clear to white
  memset(framebuf, 0xFF, FRAME_BYTES);
  rlcd_write_frame(framebuf);
}

// ---------------------------------------------------------------------------
// Write full framebuffer — matches Waveshare RLCD_Display()
// ---------------------------------------------------------------------------

static void rlcd_write_frame(const uint8_t *buf) {
  send_cmd(0x2A); send_data(0x12); send_data(0x2A);
  send_cmd(0x2B); send_data(0x00); send_data(0xC7);
  send_cmd(0x2C);
  ds_data(); cs_lo();
  SPI.writeBytes(buf, FRAME_BYTES);
  cs_hi();
}

// ---------------------------------------------------------------------------
// Serial frame receiver
// ---------------------------------------------------------------------------

static bool read_exact(uint8_t *dst, size_t n, uint32_t timeout_ms = 3000) {
  Serial.setTimeout(timeout_ms);
  return Serial.readBytes(dst, n) == n;
}

// [0xAA][0xBB][index 4B big-endian][value 1B] — patch one byte in framebuf and redraw
static void handle_patch() {
  uint8_t idxbuf[4];
  if (!read_exact(idxbuf, 4, 1000)) { Serial.write(NAK); Serial.write(0x01); return; }
  uint32_t idx = ((uint32_t)idxbuf[0] << 24) | ((uint32_t)idxbuf[1] << 16)
               | ((uint32_t)idxbuf[2] << 8)  |  (uint32_t)idxbuf[3];
  if (idx >= FRAME_BYTES) { Serial.write(NAK); Serial.write(0x02); return; }
  uint8_t value;
  if (!read_exact(&value, 1, 1000)) { Serial.write(NAK); Serial.write(0x03); return; }
  framebuf[idx] = value;
  rlcd_write_frame(framebuf);
  Serial.write(ACK);
}

static void handle_incoming() {
  uint8_t b;
  if (!read_exact(&b, 1, 100)) return;
  if (b != 0xAA) return;
  if (!read_exact(&b, 1, 100)) return;

  if (b == 0xBB) { handle_patch(); return; }
  if (b != 0x55) return;

  uint8_t lenbuf[4];
  if (!read_exact(lenbuf, 4)) { Serial.write(NAK); Serial.write(0x01); return; }
  uint32_t length = ((uint32_t)lenbuf[0] << 24) | ((uint32_t)lenbuf[1] << 16)
                  | ((uint32_t)lenbuf[2] << 8)  |  (uint32_t)lenbuf[3];
  if (length != FRAME_BYTES) { Serial.write(NAK); Serial.write(0x02); return; }

  if (!read_exact(framebuf, FRAME_BYTES, 5000)) { Serial.write(NAK); Serial.write(0x03); return; }

  uint8_t expected_sum;
  if (!read_exact(&expected_sum, 1)) { Serial.write(NAK); Serial.write(0x04); return; }
  uint8_t actual_sum = 0;
  for (size_t i = 0; i < FRAME_BYTES; i++) actual_sum += framebuf[i];
  if (actual_sum != expected_sum) { Serial.write(NAK); Serial.write(0x05); return; }

  rlcd_write_frame(framebuf);
  Serial.write(ACK);
}

// ---------------------------------------------------------------------------

void setup() {
  Serial.setRxBufferSize(32768);  // must be called before Serial.begin()
  Serial.begin(BAUD);
  pinMode(PIN_DS, OUTPUT);
  pinMode(PIN_RESET, OUTPUT);
  pinMode(PIN_CS, OUTPUT);
  cs_hi();

  SPI.begin(PIN_SCK, -1, PIN_MOSI, -1);
  SPI.setFrequency(10000000);  // 10MHz per Waveshare io_config.pclk_hz
  SPI.setDataMode(SPI_MODE0);

  rlcd_init();
}

void loop() {
  if (Serial.available()) {
    handle_incoming();
  }
}
