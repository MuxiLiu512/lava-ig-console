#!/bin/bash
# auto_render.sh — 每 10 分鐘由 launchd 執行的零 token 渲染哨兵。
# 職責：git pull → render-approved（冪等：只有「審核/文案編輯比成品新」才會真的重出）→ 有產出就 push。
# 不做需要判斷的事（餵卡、留言、成效）——那些仍由 Claude feed 排程（每日 3 次）負責。
set -u
REPO="/Users/mimo/Claude/貼文製造機器人/lava-ig-console"
DP="/Users/mimo/Library/CloudStorage/GoogleDrive-service@lava.tw/My Drive/Lava INC. Assets/02_Marketing/98_Lava-IG-AI產文系統/產出"
LOCK="/tmp/lava-ig-autorender.lock"
LOG="/tmp/lava-ig-autorender.log"
RUNMARK="/tmp/lava-ig-autorender.running"

# Python 解譯器：launchd 的 PATH 不含 anaconda，`python3` 會落到 /usr/bin/python3（無 PIL），
# 導致渲染／總檢在部分輪次靜默失敗（log 自 2026-08-02 起零星出現 ModuleNotFoundError: PIL）。
# 明確挑一個帶得動 PIL 的解譯器，挑不到就直接告警退出，不再半殘運轉。
# launchd 的 PATH 只有 /usr/bin:/bin:/usr/sbin:/sbin，沒有 homebrew。
# `timeout` 裝在 /opt/homebrew/bin（coreutils），launchd 輪次裡每一個 timeout 呼叫
# 都 127 command not found——訊號、成效、ideas-apply/pull、渲染、排版檢查全部靜默不跑，
# 只剩沒包 timeout 的零星步驟在動（2026-08-24 抓到：ideas-pull 停在 08-20，
# Jesse 的放行決定四天沒有回寫 ClickUp）。互動 shell 有 homebrew PATH，
# 所以每次手動跑都是好的——正是「手動都過、排程全死」的經典組合。
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
# 讓共用的 save() 認得「這是哨兵在寫」，不對自己誤報撞車〔2026-09-03〕
export LAVA_SENTINEL=1
if ! command -v timeout >/dev/null 2>&1; then
  echo "[$(date '+%m-%d %H:%M')] ✗ 找不到 timeout（coreutils），哨兵中止——這會讓所有步驟靜默不跑" >>"$LOG"
  exit 1
fi

PY=""
for c in /Users/mimo/opt/anaconda3/bin/python3 "$(command -v python3 2>/dev/null)" /usr/bin/python3; do
  [ -n "$c" ] && [ -x "$c" ] || continue
  if "$c" -c "import PIL" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "[$(date '+%m-%d %H:%M')] ✗ 找不到帶 PIL 的 python3，哨兵中止" >>"$LOG"
  exit 1
fi

# Drive 未掛載就靜默跳過（渲染需讀原圖）
[ -d "$DP" ] || exit 0

# 防重疊鎖（殘留超過 30 分鐘視為僵鎖，清掉；rm -rf 兼容鎖被寫成普通檔案的壞態）
if [ -e "$LOCK" ]; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then rm -rf "$LOCK" 2>/dev/null; else exit 0; fi
fi
mkdir "$LOCK" || exit 0
trap 'rm -rf "$LOCK" 2>/dev/null; rm -f "$RUNMARK" 2>/dev/null' EXIT

cd "$REPO" || exit 0

# 未完成輪次告警 〔2026-08-17 事故〕
# ingest-new 卡在 Drive 讀檔 21.5 小時，launchd 不併發啟動同一個 job → 整條線靜默停擺，
# log 也沒有新行（每步都沒跑完，沒東西可印）。「沒有訊息」與「一切正常」長得一模一樣。
# 判準用「開始了卻沒結束」而非「兩輪間隔過久」：後者會把筆電睡眠誤報成卡死，
# 睡眠時上一輪早就正常收尾、標記已清，只有真的卡死才會留下這個檔。
# 前提是每步都有 timeout（本檔各步已加），否則卡死的那輪永遠跑不到清除這一行。
if [ -f "$RUNMARK" ]; then
  STUCK=$(( ($(date +%s) - $(stat -f %m "$RUNMARK")) / 60 ))
  LASTSTEP=$(cat "$RUNMARK" 2>/dev/null)
  echo "[$(date '+%m-%d %H:%M')] ⚠ 上一輪未完成（停在 ${LASTSTEP}，${STUCK} 分鐘前）" >>"$LOG"
  timeout 120 "$PY" scripts/sync_console.py alert "哨兵上一輪未跑完就中斷（停在「${LASTSTEP}」，${STUCK} 分鐘前）。渲染／入料／成效在這段期間停止，請確認佇列狀態。" >>"$LOG" 2>&1
fi
echo "啟動" >"$RUNMARK"

# 自動化慣例開關〔2026-09-03，學 Stanley 的 Rituals〕
# 哨兵每輪做 22 件事，過去全部寫死在這支腳本裡——Jesse 看不到也關不掉。
# 現在每個步驟先問一次 data/rituals.json。關掉的步驟會在日誌留一行，
# 不是靜默跳過（靜默跳過的話，你會以為它壞了）。
# 用輸出字串判斷，不用退出碼——退出碼會與「腳本本身跑失敗」混淆：
# 第一版寫 sys.exit(1) 代表關閉，外層卻用 `|| return 0` 接住執行失敗，
# 結果「刻意回報關閉」也被當成失敗、一律視為開啟，開關等於沒作用。
ritual_on() {
  local v
  v=$("$PY" - "$1" <<'RITPY' 2>/dev/null
import json, sys
try:
    for r in json.load(open("data/rituals.json", encoding="utf-8")).get("rituals", []):
        if r.get("id") == sys.argv[1]:
            print("off" if r.get("enabled", True) is False else "on"); break
    else:
        print("on")
except Exception:
    print("on")      # 讀不到設定就照跑，開關壞掉不該讓產線停擺
RITPY
)
  [ "$v" != "off" ]
}
ritual_skip() {
  echo "[$(date '+%m-%d %H:%M')] ⏸ 慣例「$1」已由你關閉，本輪跳過" >>"$LOG"
}
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
    "$PY" scripts/sync_console.py alert "哨兵停擺：git pull 連續 6 輪失敗（約 1 小時）。渲染／入料／對帳全部停止，需人工排查工作區狀態。" >>"$LOG" 2>&1
  fi
  exit 0
fi
rm -f "$FAILFILE"
# stash pop 撞衝突會把 <<<<<<< 標記寫進 posts.json（2026-08-11 實際發生，操控室排程資料一度壞掉）。
# 衝突時一律以遠端為準並保留 stash 供人工比對，絕不留壞 JSON 在工作區。
if [ "$STASHED" = 1 ]; then
  if ! git stash pop -q >>"$LOG" 2>&1; then
    # 2026-08-12 實測：`--theirs` 在 stash pop 情境指的是 **stash 那一側**（哨兵舊版），
    # 不是遠端。原寫法會把操控室剛存的核准／排程／文案編輯無聲換回舊版，
    # 而且產出是合法 JSON（無衝突標記），衝突標記檢查完全抓不到。
    # pull 已經完成，HEAD 就是遠端最新 → 取 HEAD 才是「以遠端為準」。
    git checkout HEAD -- . >>"$LOG" 2>&1 || true
    git reset -q >>"$LOG" 2>&1
    echo "[$(date '+%m-%d %H:%M')] ⚠ stash pop 衝突：已取遠端版本，本地變更留在 stash@{0}" >>"$LOG"
    "$PY" scripts/sync_console.py alert "哨兵 stash pop 衝突：已保留遠端版本，本地暫存在 stash@{0}，請人工確認是否有未同步的操控室操作。" >>"$LOG" 2>&1
  fi
fi

# 訊號蒐集（每天第一輪跑一次即可；來源清單在本機，加來源不用動 n8n）
SIGDATE=$(date '+%Y-%m-%d')
if [ ! -f "data/signals/${SIGDATE}.json" ]; then
  echo "訊號蒐集" >"$RUNMARK"
  SIG=$(timeout 600 "$PY" scripts/collect_signals.py 2>&1 | head -1)
  echo "[$(date '+%m-%d %H:%M')] 訊號 $SIG" >>"$LOG"
fi

# IG 成效（每天最多試一次；戳記用 /tmp 而非 insights.json 的 updated_at——
# 缺 token 或 API 失敗時 updated_at 不會前進，會變成每 10 分鐘重試並刷爆 log）。
# 2026-08-17 起改本機抓：n8n WF11 每天照跑，但它的輸出沒有任何寫入端，成效實際停在 7/27。
INS_STAMP="/tmp/lava-ig-insights.$(date '+%Y-%m-%d')"
if [ ! -f "$INS_STAMP" ]; then
  touch "$INS_STAMP"
  echo "IG 成效" >"$RUNMARK"
  IGI=$(timeout 300 "$PY" scripts/ig_insights.py 2>&1)
  echo "$IGI" | grep -E "✓ 成效|✗|！缺 ig_token" | head -2 | sed "s/^/[$(date '+%m-%d %H:%M')] 成效/" >>"$LOG"
  # 成效自己 commit：本輪若沒有渲染產出，下方的 push 不會觸發，
  # insights.json 就只留在本機，操控室（GitHub Pages 讀 repo）永遠看不到新數字。
  if echo "$IGI" | grep -q "✓ 成效"; then
    git add data/insights.json data/posts.json 2>/dev/null
    git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512 commit -q -m "auto-insights: IG 成效每日快照" \
      -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" >>"$LOG" 2>&1 \
      && git push --quiet origin main >>"$LOG" 2>&1
  fi
fi

# GitHub PAT 每日 ping ＋ 正式站冒煙測 〔2026-08-19 事故：PAT 過期，操控室整站 401，
# 死了多久沒人知道——IG token 有每日 ping，GitHub PAT 沒有。憑證有壽命，每一支都要有 ping。
# 冒煙測走「訪客路徑」（無認證讀），等同真實使用者打開正式站的第一個請求。〕
GH_STAMP="/tmp/lava-ig-ghpat.$(date '+%Y-%m-%d')"
if [ ! -f "$GH_STAMP" ]; then
  touch "$GH_STAMP"
  echo "PAT 檢查" >"$RUNMARK"
  GHTOK=$("$PY" -c "import json;print(json.load(open('.sync.json')).get('token',''))" 2>/dev/null)
  if [ -n "$GHTOK" ]; then
    CODE=$(curl -s --max-time 20 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $GHTOK" https://api.github.com/user)
    if [ "$CODE" = "401" ]; then
      echo "[$(date '+%m-%d %H:%M')] ⚠ GitHub PAT 已失效（401）" >>"$LOG"
      timeout 120 "$PY" scripts/sync_console.py alert "GitHub PAT 失效（401）：操控室寫入停用中（讀取自動降級無認證）。請產新的 fine-grained PAT（Contents 讀寫、僅 lava-ig-console），更新操控室 ⚙︎ 與 .sync.json 的 token。" >>"$LOG" 2>&1
    fi
  fi
  PC=$(curl -s --max-time 20 -o /dev/null -w '%{http_code}' https://muxiliu512.github.io/lava-ig-console/review.html)
  DC=$(curl -s --max-time 20 -o /dev/null -w '%{http_code}' -H "Accept: application/vnd.github.raw" "https://api.github.com/repos/MuxiLiu512/lava-ig-console/contents/data/posts.json?ref=main")
  if [ "$PC" != "200" ] || [ "$DC" != "200" ]; then
    echo "[$(date '+%m-%d %H:%M')] ⚠ 冒煙測失敗 Pages=$PC data=$DC" >>"$LOG"
    timeout 120 "$PY" scripts/sync_console.py alert "正式站冒煙測失敗：Pages 回 $PC、無認證資料讀取回 $DC。操控室可能對訪客整站不可用。" >>"$LOG" 2>&1
  fi
fi

# 截圖策展：新稿的 visual_refs 實地截圖（素材線 v2；在入料前跑，餵入時 SHOT 即在池）
echo "截圖策展" >"$RUNMARK"
# --topup：已有舊圖的 slide 也補抓一輪 Apify 候選，兩來源並存讓 Jesse 比較
# （2026-08-27：換源後既有稿一張都沒被重抓，所以「看不出品質差異」）。
FRG=$(timeout 700 "$PY" scripts/sync_console.py forage-pending --limit 2 --topup 2>&1)
echo "$FRG" | grep -E "→ forage|✓ slide|處理 [1-9]|✗" | sed "s/^/[$(date '+%m-%d %H:%M')] /" >>"$LOG"

# 書榜爬取（每天一次）〔2026-08-31 crawl4ai 上線〕
# 雷達的「書與趨勢榜」題型從二手報導升級成第一手榜單。跑在哨兵層是因為
# 需要完整 Chromium（n8n 雲端跑不了）。venv 缺席就跳過並記錄，不擋主流程。
TC_STAMP="/tmp/lava-ig-trendcrawl.$(date '+%Y-%m-%d')"
C4AI_PY="$REPO/.venv-c4ai/bin/python"
if ! ritual_on trend_crawl; then ritual_skip "每天爬書榜"; touch "$TC_STAMP"; fi
if [ ! -f "$TC_STAMP" ] && [ -x "$C4AI_PY" ]; then
  touch "$TC_STAMP"
  echo "書榜爬取" >"$RUNMARK"
  TCR=$(timeout 240 "$C4AI_PY" scripts/trend_crawl.py 2>&1 | tail -6)
  echo "$TCR" | grep -E "✓|⏭|寫入" | sed "s/^/[$(date '+%m-%d %H:%M')] 書榜/" >>"$LOG"
  if [ -n "$(git status --porcelain data/trend_crawl.json)" ]; then
    git add data/trend_crawl.json
    git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512 commit -q -m "auto-crawl: 書榜快照" \
      -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" >>"$LOG" 2>&1 \
      && git push --quiet origin main >>"$LOG" 2>&1
  fi
elif [ ! -f "$TC_STAMP" ]; then
  touch "$TC_STAMP"
  echo "[$(date '+%m-%d %H:%M')] 書榜：.venv-c4ai 缺席，跳過（重建法見 scripts/trend_crawl.py 尾註）" >>"$LOG"
fi

# 學習迴路（每天一次）〔2026-08-25 事故〕
# iterate_harness 把「退回意見」轉成 config/style-notes.md 的規則（低風險自動生效、
# 高風險轉提案待審），WF01 撰稿時會讀 style-notes。但哨兵從來沒有呼叫它——
# 16 筆回饋只有 1 筆被消化，最後一則提案停在 7/15。於是 Jesse 退了什麼、
# 系統完全不知道，同樣的問題（AI 用語、素材重複、選圖不相關）無限重演。
ITR_STAMP="/tmp/lava-ig-iterate.$(date '+%Y-%m-%d')"
if [ ! -f "$ITR_STAMP" ]; then
  touch "$ITR_STAMP"
  echo "學習迴路" >"$RUNMARK"
  # 迭代四段：搜集特徵×成效 → 假說評估 → 消化回饋 → 產生規則／提案。
  # 順序不能反：iterate_harness 讀 metrics.json，那份要先由 learn_features 產出，
  # 否則成效那條手臂永遠沒有資料（2026-08-26 之前 metrics.json entries 一直是 0）。
  LFT=$(timeout 300 "$PY" scripts/learn_features.py 2>&1 | tail -4)
  echo "$LFT" | grep -E "已寫入|樣本" | sed "s/^/[$(date '+%m-%d %H:%M')] 特徵/" >>"$LOG"
  HYP=$(timeout 300 "$PY" scripts/hypotheses.py 2>&1 | tail -12)
  echo "$HYP" | grep -E "✅|❌|登記簿已更新" | sed "s/^/[$(date '+%m-%d %H:%M')] 假說/" >>"$LOG"
  ITR=$(timeout 300 "$PY" scripts/iterate_harness.py 2>&1 | tail -6)
  echo "$ITR" | grep -E "迭代摘要|⚙︎|✅|↩" | sed "s/^/[$(date '+%m-%d %H:%M')] 迭代/" >>"$LOG"
  if [ -n "$(git status --porcelain config/ data/)" ]; then
    git add config/ data/proposals.json data/reviews.json data/iterate_log.json data/metrics.json data/hypotheses.json 2>/dev/null
    git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512 commit -q -m "auto-iterate: 消化審核回饋" \
      -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" >>"$LOG" 2>&1 \
      && git push --quiet origin main >>"$LOG" 2>&1
  fi
fi

# 卡彈偵測〔2026-09-01 Jesse：「能做 schedule tasks 確認有沒有卡彈的貼文嗎」〕
# 每 3 小時一次：自己找出停住的貼文，嚴重級才推 LINE（警告級天天有，會變噪音）。
# 過去都是 Jesse 自己發現不對才回報——白夜行卡了 6 天沒人知道。偵測是系統的責任。
SK_STAMP="/tmp/lava-ig-stuck.$(date '+%Y-%m-%d-%H')"
if ! ritual_on stuck_check; then ritual_skip "自己找卡住的稿"; touch "$SK_STAMP"; fi
if [ ! -f "$SK_STAMP" ] && [ "$(( 10#$(date '+%H') % 3 ))" -eq 0 ]; then
  touch "$SK_STAMP"
  echo "卡彈偵測" >"$RUNMARK"
  STK=$(timeout 120 "$PY" scripts/stuck_check.py 2>&1)
  echo "$STK" | grep -E "卡彈 [0-9]+ 件|✓ 沒有卡住|已推 LINE|! LINE" | sed "s/^/[$(date '+%m-%d %H:%M')] 卡彈/" >>"$LOG"
fi

# 圖像策展（WF14 受眾視角）〔2026-09-01 Jesse：把 TMDB 劇照也接進策展員〕
# 入料後所有候選都在本機，一次策展涵蓋劇照＋截圖；視覺模型看得出海報與劇照的差別，
# 那正是本機啟發式分不出來的。只重排不刪圖，最終仍由人選。每輪最多 1 篇（省額度）。
echo "圖像策展" >"$RUNMARK"
if ritual_on curate; then
CUR=$(timeout 420 "$PY" scripts/sync_console.py curate-post --limit 1 2>&1)
else CUR=""; ritual_skip "幫你排選圖順序"; fi
echo "$CUR" | grep -E "→ 策展|✓ 策展|策展完成：[1-9]|!" | sed "s/^/[$(date '+%m-%d %H:%M')] 策展/" >>"$LOG"

# 重掃缺料：把上一步（或前幾輪）補到的 SHOT 素材讀回 posts.json。
# forage 只把檔案寫進 Drive 的「底圖」資料夾，ingest-new 又只吃「不在 posts.json 的卡」，
# 已入板的稿因此永遠不會被重讀——2026-08-25 七篇稿掛在「缺料」不會自己好，
# 補圖每輪都在跑、每輪都白跑。這一步就是接上那個斷點。
echo "重掃缺料" >"$RUNMARK"
RFS=$(timeout 600 "$PY" scripts/sync_console.py refresh-candidates --limit 3 2>&1)
echo "$RFS" | grep -E "↻|重掃完成：[1-9]|⏭" | sed "s/^/[$(date '+%m-%d %H:%M')] /" >>"$LOG"

# 事件折疊〔2026-08-30 脫離 ClickUp〕：操控台的每個決定（events/pending/）
# 折疊成狀態變化；idea 放行直接觸發 WF01 撰稿。ideas-apply（勾 ClickUp）退役。
echo "事件折疊" >"$RUNMARK"
EVA=$(timeout 180 "$PY" scripts/sync_console.py events-apply 2>&1)
echo "$EVA" | grep -E "✓|⚠|折疊完成" | sed "s/^/[$(date '+%m-%d %H:%M')] 事件/" >>"$LOG"
# 折疊必須立刻 commit＋push〔2026-09-01 事故〕：事件檔從 pending 移到 applied 的
# 檔案異動原本沒有任何 commit 路徑收，工作區累積髒檔 → push 全卡 → 決定折了
# 但遠端看不到 → 前端重整又把稿抓回來（「排時間無限迴圈」的第二隻腳）。
if [ -n "$(git status --porcelain events/ data/posts.json data/ideas.json data/reviews.json)" ]; then
  git add events/ data/posts.json data/ideas.json data/reviews.json 2>/dev/null
  git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512 commit -q -m "auto-events: 折疊決定" \
    -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" >>"$LOG" 2>&1 \
    && git push --quiet origin main >>"$LOG" 2>&1
fi
# 靈感收件匣：WF05 雷達 → n8n 資料表 → 這裡拉進 ideas.json（ClickUp 完全出局）。
IDE=$(timeout 120 "$PY" scripts/sync_console.py radar-pull 2>&1)
echo "$IDE" | grep -E "✓ 收件匣|! " | sed "s/^/[$(date '+%m-%d %H:%M')] /" >>"$LOG"

# 入料：在製中卡的新草稿自動餵進操控室。
# limit 2 → 3：2026-08-25 積壓 6 篇時，每輪只吃 2 張又碰上 Drive 暫時性讀檔錯誤，
# 佇列排不完；timeout 隨之從 420 拉到 700（每篇約 2 分鐘，含重試）。
echo "入料" >"$RUNMARK"
ING=$(timeout 700 "$PY" scripts/sync_console.py ingest-new --limit 3 2>&1)
echo "[$(date '+%m-%d %H:%M')] $ING" | grep -E "✓ posts|入料完成：[1-9]|⏭ 餵入|Error" >>"$LOG"

echo "渲染" >"$RUNMARK"
OUT=$(timeout 600 "$PY" scripts/sync_console.py render-approved 2>&1)
echo "[$(date '+%m-%d %H:%M')] $OUT" | grep -E "✓RENDERED|⏭|Error|Traceback" >>"$LOG"

# 圖上實際呈現的逐行文字（供操控室與文字框對照，避免「不知道哪邊才是正確的」）
echo "逐行文字" >"$RUNMARK"
timeout 300 "$PY" scripts/sync_console.py rendered-lines >/dev/null 2>&1

# 排版回歸檢查（零成本，機械）：行尾標點／詞中斷行／缺字——用引擎本身的斷行函式重算驗證
echo "排版檢查" >"$RUNMARK"
TYP=$(timeout 300 "$PY" scripts/check_typography.py --write 2>&1 | tail -8)
echo "$TYP" | grep -E "違規 [1-9]|稿檔損毀|🔴" | sed "s/^/[$(date '+%m-%d %H:%M')] 排版/" >>"$LOG"

# 文案禁句（機械，正則）：破折號、「不是…而是」、對話式開場、產品禁用詞。
# 規則早就寫在 style-notes 與 WF01 審查裡，但實測八篇稿全部違規——因為 WF01
# 的流程是「審查不過 → 重寫一輪 → 直接存檔」，重寫結果從未被重新審查。
# 這種確定性規則本來就該用正則擋，不該交給 LLM 判斷。
echo "文案禁句" >"$RUNMARK"
CPY=$(timeout 300 "$PY" scripts/copy_check.py 2>&1 | tail -10)
echo "$CPY" | grep -E "🔴|⚠" | sed "s/^/[$(date '+%m-%d %H:%M')] 文案/" >>"$LOG"

# 禁句自動修：破折號這種「改法唯一」的違規直接機械修掉，不佔用人工。
# 一天三篇的瓶頸不在排程器而在閘門——10 篇待發稿有 7 篇卡在禁句、共 73 處
#（Jesse 2026-08-27 要求提高產量時抓到）。判斷性的違規不碰，留給人。
echo "禁句自動修" >"$RUNMARK"
CFX=$(timeout 300 "$PY" scripts/copy_fix.py 2>&1 | tail -6)
echo "$CFX" | grep -E "→ 0|已修" | sed "s/^/[$(date '+%m-%d %H:%M')] 修文/" >>"$LOG"

# 事實查核（機械，不需 LLM）：抓文案裡的數字與研究引用，驗每一條有沒有活著且對得上的出處。
# 起因是 2026-08-23 的 Jason Arday 靈感卡：宣稱「今天台灣熱搜」但當日榜上沒有，
# 年齡數字也與英媒說法不符，唯一出處還是每天會變的 trends 首頁。
# 結果寫進 posts.json 的 fact 欄，操控室「事實」閘門讀它，I9 擋住未過的稿排程。
echo "事實查核" >"$RUNMARK"
FCT=$(timeout 600 "$PY" scripts/fact_check.py 2>&1 | tail -12)
echo "$FCT" | grep -E "🔴|⚠|\[block\]" | sed "s/^/[$(date '+%m-%d %H:%M')] 事實/" >>"$LOG"

# 成篇視覺總檢：有新成品才跑（撞主體/浮水印/不可讀/出處異常——逐張閘門看不出來的）
if echo "$OUT" | grep -q "✓RENDERED"; then
  echo "成篇總檢" >"$RUNMARK"
  QA=$(timeout 600 "$PY" scripts/sync_console.py post-qa 2>&1)
  echo "$QA" | grep -E "🔴|🟡|✅|\[block\]" | sed "s/^/[$(date '+%m-%d %H:%M')] /" >>"$LOG"
fi

# 資料不變量（修法 B）：違反＝立刻告警。「永遠不准發生」的狀態清單見 verify_invariants.py
echo "不變量" >"$RUNMARK"
INV=$(timeout 60 "$PY" scripts/verify_invariants.py 2>&1)

# 陳舊稽核（2026-08-25）：不變量問「狀態合法嗎」，這支問「畫面與文件的宣稱還成立嗎」。
# 陳舊不是壞掉、不該讓哨兵變紅，所以只印不擋（退出碼恆 0）。
# 來源紀律：海巡機器人的模型 A/B 定案後面板仍每天要求裁決，問了 25 天——
# 產生訊號有人做、讓訊號退場沒人做。
timeout 60 "$PY" scripts/verify_staleness.py 2>&1 | sed 's/^/[stale] /' || true
if echo "$INV" | grep -q "🔴"; then
  echo "$INV" | sed "s/^/[$(date '+%m-%d %H:%M')] /" >>"$LOG"
  timeout 120 "$PY" scripts/sync_console.py alert "資料不變量違反：$(echo "$INV" | head -3 | tr '\n' '；')請立即檢查 posts.json。" >>"$LOG" 2>&1
fi

# 發佈對帳（ClickUp 發佈完成 → posts.json published）；.sync.json 無真 token 時內部自動略過
echo "發佈對帳" >"$RUNMARK"
REC=$(timeout 300 "$PY" scripts/sync_console.py reconcile-published 2>&1)
echo "$REC" | grep -E "✓|published" >>"$LOG"
echo "$REC" | grep -q "✓" && { git add data/ docs/finals/ assets/ 2>/dev/null; git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512 commit -q -m "auto-reconcile: 發佈對帳" >>"$LOG" 2>&1; git push --quiet origin main >>"$LOG" 2>&1; }

# 已發佈 → 回填 02_Marketing/05_貼文規劃（行銷側的完整檔案庫；冪等，補過不重複）
echo "Marketing 回填" >"$RUNMARK"
MKA=$(timeout 300 "$PY" scripts/sync_console.py marketing-archive 2>&1)
echo "$MKA" | grep -E "✓ .*→|⏭" | sed "s/^/[$(date '+%m-%d %H:%M')] /" >>"$LOG"

# 心跳檔（工作台健康列的資料源，§3.2）：每輪寫入本輪結果；
# 有工作 push 就搭便車進 repo，安靜時最多 55 分鐘推一次專用 commit。
# 健康列的判準：心跳 >70 分鐘＝哨兵斷了（Drive 未掛載時腳本 26 行提前退出、
# 心跳凍結，也會被同一個判準抓到——這正是「靜默 exit 0」十天前的坑）。
echo "心跳" >"$RUNMARK"
OUT="$OUT" ING="$ING" TYP="$TYP" "$PY" - <<'PYEOF' 2>>"$LOG"
import json, os, datetime, re
out=os.environ.get("OUT",""); ing=os.environ.get("ING",""); typ=os.environ.get("TYP","")
errs=[]
try:
    with open("/tmp/lava-ig-autorender.log", encoding="utf-8", errors="replace") as f:
        tail=f.readlines()[-40:]
    today=datetime.date.today().strftime("%m-%d")
    errs=[l.strip()[:160] for l in tail if l.startswith("[%s"%today) and ("⚠" in l or "✗" in l or "🔴" in l)][-5:]
except Exception:
    pass
hb={"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    "drive": True,
    "rendered": out.count("✓RENDERED"),
    "ingested": len(re.findall(r"✓ posts", ing)),
    "typography_ok": "違規 0 處" in typ,
    "errors": errs}
json.dump(hb, open("data/heartbeat.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
PYEOF

if echo "$OUT$ING$TYP$IDE" | grep -qE "✓RENDERED|✓ posts|✎ typography 欄位寫回 [1-9]|✓ 靈感"; then
  git add data/ docs/finals/ assets/ 2>/dev/null
  git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512 commit -q -m "auto-render: 偵測到新審核/文案修改，重出成品" \
    -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" >>"$LOG" 2>&1
  git push --quiet origin main >>"$LOG" 2>&1
fi
# 心跳專用 commit（本輪沒有工作 push 時才會走到；55 分鐘節流）
HBSTAMP="/tmp/lava-ig-hb.pushed"
if [ -n "$(git status --porcelain data/heartbeat.json 2>/dev/null)" ]; then
  if [ ! -f "$HBSTAMP" ] || [ -n "$(find "$HBSTAMP" -mmin +55 2>/dev/null)" ]; then
    git add data/heartbeat.json
    git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512 commit -q -m "auto-heartbeat" >>"$LOG" 2>&1 \
      && git push --quiet origin main >>"$LOG" 2>&1 && touch "$HBSTAMP"
  fi
fi
exit 0
