-- outdoor.computer SQLite schema
-- Long-format `samples` table: adding a new metric is one INSERT, no migrations.

CREATE TABLE IF NOT EXISTS samples (
  ts         INTEGER NOT NULL,           -- unix seconds
  source     TEXT    NOT NULL,           -- 'slate' | 'starlink' | 'weather' | 'local' | 'derived'
  metric     TEXT    NOT NULL,           -- 'throughput_dn' | 'latency_ms' | 'status' | ...
  value_num  REAL,                       -- numeric value if applicable
  value_text TEXT                        -- string value if applicable (e.g. 'online'/'degraded'/'offline')
);
CREATE INDEX IF NOT EXISTS samples_ts          ON samples(ts);
CREATE INDEX IF NOT EXISTS samples_metric_ts   ON samples(metric, ts);
CREATE INDEX IF NOT EXISTS samples_source_ts   ON samples(source, ts);

CREATE TABLE IF NOT EXISTS bulletin (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       INTEGER NOT NULL,
  username TEXT    NOT NULL,
  message  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS bulletin_ts ON bulletin(ts);

CREATE TABLE IF NOT EXISTS events (
  ts      INTEGER NOT NULL,
  kind    TEXT    NOT NULL,              -- 'status_change' | 'poller_error' | 'startup' | ...
  details TEXT
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
