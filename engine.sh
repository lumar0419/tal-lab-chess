#!/bin/sh
# macOS / Linux용: 체스 GUI에 이 파일을 엔진으로 등록하세요 (처음 한 번: chmod +x engine.sh)
exec python3 "$(dirname "$0")/uci.py" "$@"
