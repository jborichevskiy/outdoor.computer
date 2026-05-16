#!/usr/bin/env bash
# Spin up the outdoor.computer tmux session.
# One window per service. Attach with: tmux attach -t outdoor
set -euo pipefail

cd "$(dirname "$0")"
REPO="$PWD"
SESSION="outdoor"

# Use the venv's python if it exists, else system python3.
PY="$REPO/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session '$SESSION' already exists. Attach with: tmux attach -t $SESSION"
  exit 0
fi

# Each window: cd into code/ so `from db import ...` works without PYTHONPATH games.
tmux new-session  -d -s "$SESSION" -n poll-slate     -c "$REPO/code" \
  "$PY -u poll/slate.py"

tmux new-window  -t "$SESSION"     -n poll-starlink  -c "$REPO/code" \
  "$PY -u poll/starlink.py"

tmux new-window  -t "$SESSION"     -n poll-weather   -c "$REPO/code" \
  "$PY -u poll/weather.py"

tmux new-window  -t "$SESSION"     -n poll-local     -c "$REPO/code" \
  "$PY -u poll/local.py"

tmux new-window  -t "$SESSION"     -n web            -c "$REPO/code" \
  "$PY -u web/app.py"

echo "tmux session '$SESSION' started."
echo "Watch live logs: tmux attach -t $SESSION"
echo "(Ctrl-b then 0..4 to switch windows; Ctrl-b d to detach.)"
