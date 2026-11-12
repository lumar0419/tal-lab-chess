#!/usr/bin/env bash
cd "$(dirname "$0")"
exec python3 web_server.py "$@"
