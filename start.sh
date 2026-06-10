#!/bin/sh
set -e
if [ "$APP_MODE" = "web" ]; then
  exec python web_main.py
fi
exec python main.py
