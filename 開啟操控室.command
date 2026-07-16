#!/bin/bash
# 地端首頁一鍵開啟：啟動本地伺服器（若未啟動）→ 開瀏覽器到貼文生產首頁。
# 用法：在 Finder 雙擊本檔。首次可能需右鍵「打開」以通過 Gatekeeper。
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=8765
cd "$DIR"

# 若 8765 已有伺服器就不重複啟動
if ! curl -s -o /dev/null "http://localhost:$PORT/docs/home.html"; then
  echo "啟動本地伺服器 http://localhost:$PORT …"
  (python3 -m http.server "$PORT" >/tmp/lava_console_server.log 2>&1 &)
  sleep 1
fi

open "http://localhost:$PORT/docs/home.html"
echo "已開啟貼文生產首頁。關閉伺服器：pkill -f 'http.server $PORT'"
