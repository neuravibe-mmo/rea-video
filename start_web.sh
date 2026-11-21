#!/usr/bin/env bash
# Khởi động rea-video Web Studio trên localhost:8888
DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${1:-8888}"
echo "Đang khởi động rea-video Web Studio..."
exec python3 -u "$DIR/web_server.py" --port "$PORT"
