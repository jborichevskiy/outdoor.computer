#!/usr/bin/env bash
# Kill the outdoor.computer tmux session.
set -euo pipefail

SESSION="outdoor"
if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
  echo "killed tmux session '$SESSION'"
else
  echo "no tmux session '$SESSION' running"
fi
