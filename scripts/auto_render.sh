#!/bin/bash
# auto_render.sh — 每 10 分鐘由 launchd 執行的零 token 渲染哨兵。
# 職責：git pull → render-approved（冪等：只有「審核/文案編輯比成品新」才會真的重出）→ 有產出就 push。
# 不做需要判斷的事（餵卡、留言、成效）——那些仍由 Claude feed 排程（每日 3 次）負責。
set -u
REPO="/Users/mimo/Desktop/Claude/貼文製造機器人/lava-ig-console"
DP="/Users/mimo/Library/CloudStorage/GoogleDrive-service@lava.tw/My Drive/Lava INC. Assets/02_Marketing/98_Lava-IG-AI產文系統/產出"
LOCK="/tmp/lava-ig-autorender.lock"
LOG="/tmp/lava-ig-autorender.log"

# Drive 未掛載就靜默跳過（渲染需讀原圖）
[ -d "$DP" ] || exit 0

# 防重疊鎖（殘留超過 30 分鐘視為僵鎖，清掉）
if [ -d "$LOCK" ]; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then rmdir "$LOCK" 2>/dev/null; else exit 0; fi
fi
mkdir "$LOCK" || exit 0
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

cd "$REPO" || exit 0
git pull --rebase --quiet origin main >>"$LOG" 2>&1 || { git rebase --abort >/dev/null 2>&1; exit 0; }

OUT=$(python3 scripts/sync_console.py render-approved 2>&1)
echo "[$(date '+%m-%d %H:%M')] $OUT" | grep -E "✓RENDERED|⏭|Error|Traceback" >>"$LOG"

if echo "$OUT" | grep -q "✓RENDERED"; then
  git add -A
  git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512 commit -q -m "auto-render: 偵測到新審核/文案修改，重出成品" \
    -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" >>"$LOG" 2>&1
  git push --quiet origin main >>"$LOG" 2>&1
fi
exit 0
