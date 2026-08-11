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

# 防重疊鎖（殘留超過 30 分鐘視為僵鎖，清掉；rm -rf 兼容鎖被寫成普通檔案的壞態）
if [ -e "$LOCK" ]; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then rm -rf "$LOCK" 2>/dev/null; else exit 0; fi
fi
mkdir "$LOCK" || exit 0
trap 'rm -rf "$LOCK" 2>/dev/null' EXIT

cd "$REPO" || exit 0
# 工作區髒污（未提交的腳本改動）曾讓 pull 每輪失敗、整條線靜默停擺兩天（2026-08-03~05）。
# 改為：先 stash 再 pull，成功後還原；失敗才放棄本輪。哨兵不再被未提交檔案卡死。
STASHED=0
if [ -n "$(git status --porcelain)" ]; then
  git stash push -q -u -m "autorender-$(date +%s)" >>"$LOG" 2>&1 && STASHED=1
fi
FAILFILE="/tmp/lava-ig-pullfail.count"
if ! git pull --rebase --quiet origin main >>"$LOG" 2>&1; then
  git rebase --abort >/dev/null 2>&1
  [ "$STASHED" = 1 ] && git stash pop -q >>"$LOG" 2>&1
  N=$(( $(cat "$FAILFILE" 2>/dev/null || echo 0) + 1 ))
  echo "$N" >"$FAILFILE"
  echo "[$(date '+%m-%d %H:%M')] ⚠ git pull 失敗（連續 $N 輪），本輪略過" >>"$LOG"
  # 連續 6 輪（≈1 小時）＝哨兵實質停擺 → 自報告警到 ClickUp 告警日誌卡，避免再靜默兩天
  if [ "$N" = 6 ]; then
    python3 scripts/sync_console.py alert "哨兵停擺：git pull 連續 6 輪失敗（約 1 小時）。渲染／入料／對帳全部停止，需人工排查工作區狀態。" >>"$LOG" 2>&1
  fi
  exit 0
fi
rm -f "$FAILFILE"
# stash pop 撞衝突會把 <<<<<<< 標記寫進 posts.json（2026-08-11 實際發生，操控室排程資料一度壞掉）。
# 衝突時一律以遠端為準並保留 stash 供人工比對，絕不留壞 JSON 在工作區。
if [ "$STASHED" = 1 ]; then
  if ! git stash pop -q >>"$LOG" 2>&1; then
    git checkout --theirs -- . >>"$LOG" 2>&1 || true
    git checkout -- data/ >>"$LOG" 2>&1 || true
    git reset -q >>"$LOG" 2>&1
    echo "[$(date '+%m-%d %H:%M')] ⚠ stash pop 衝突：已取遠端版本，本地變更留在 stash@{0}" >>"$LOG"
    python3 scripts/sync_console.py alert "哨兵 stash pop 衝突：已保留遠端版本，本地暫存在 stash@{0}，請人工確認是否有未同步的操控室操作。" >>"$LOG" 2>&1
  fi
fi

# 截圖策展：新稿的 visual_refs 實地截圖（素材線 v2；在入料前跑，餵入時 SHOT 即在池）
FRG=$(timeout 700 python3 scripts/sync_console.py forage-pending --limit 2 2>&1)
echo "$FRG" | grep -E "→ forage|✓ slide|處理 [1-9]|✗" | sed "s/^/[$(date '+%m-%d %H:%M')] /" >>"$LOG"

# 入料：在製中卡的新草稿自動餵進操控室（每輪最多 2 張，避免單輪過長）
ING=$(python3 scripts/sync_console.py ingest-new --limit 2 2>&1)
echo "[$(date '+%m-%d %H:%M')] $ING" | grep -E "✓ posts|入料完成：[1-9]|⏭ 餵入|Error" >>"$LOG"

OUT=$(python3 scripts/sync_console.py render-approved 2>&1)
echo "[$(date '+%m-%d %H:%M')] $OUT" | grep -E "✓RENDERED|⏭|Error|Traceback" >>"$LOG"

# 成篇視覺總檢：有新成品才跑（撞主體/浮水印/不可讀/出處異常——逐張閘門看不出來的）
if echo "$OUT" | grep -q "✓RENDERED"; then
  QA=$(timeout 600 python3 scripts/sync_console.py post-qa 2>&1)
  echo "$QA" | grep -E "🔴|🟡|✅|\[block\]" | sed "s/^/[$(date '+%m-%d %H:%M')] /" >>"$LOG"
fi

# 發佈對帳（ClickUp 發佈完成 → posts.json published）；.sync.json 無真 token 時內部自動略過
REC=$(python3 scripts/sync_console.py reconcile-published 2>&1)
echo "$REC" | grep -E "✓|published" >>"$LOG"
echo "$REC" | grep -q "✓" && { git add -A; git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512 commit -q -m "auto-reconcile: 發佈對帳" >>"$LOG" 2>&1; git push --quiet origin main >>"$LOG" 2>&1; }

if echo "$OUT$ING" | grep -qE "✓RENDERED|✓ posts"; then
  git add -A
  git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512 commit -q -m "auto-render: 偵測到新審核/文案修改，重出成品" \
    -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" >>"$LOG" 2>&1
  git push --quiet origin main >>"$LOG" 2>&1
fi
exit 0
