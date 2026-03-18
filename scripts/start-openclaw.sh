#!/bin/sh
set -eu

OPENCLAW_HOME_DIR="${OPENCLAW_HOME:-/app/.openclaw}"
CONFIG_PATH="$OPENCLAW_HOME_DIR/openclaw.json"

mkdir -p "$OPENCLAW_HOME_DIR"

if [ ! -f "$CONFIG_PATH" ]; then
  cp /app/openclaw/openclaw.json.example "$CONFIG_PATH"
fi

exec openclaw gateway run
