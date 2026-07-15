#!/usr/bin/env bash
# =============================================================================
# push_files.sh — 把 console repo 內指定的多個檔/資料夾安全推上 GitHub。
# 沿用 lava-live/push_json.sh 的設計：token 遮蔽、無變更跳過、撞車 fetch+rebase 重試。
#
# 用法:  bash push_files.sh "commit 訊息" <path1> [path2 ...]
# 範例:  bash push_files.sh "pipeline: 新增貼文 20260716" data/posts.json assets/20260716-xxx
#
# 讀 repo 根目錄的 .sync.json（git-ignored）：{owner, repo, branch, token}。
# 沒有 .sync.json：只留本機、不推。
# =============================================================================
set -euo pipefail
MSG="${1:?用法: push_files.sh <commit訊息> <path...>}"; shift
[ "$#" -ge 1 ] || { echo "✗ 至少要指定一個路徑"; exit 1; }

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SYNC="$REPO/.sync.json"
if [ ! -f "$SYNC" ]; then echo "（無 .sync.json）已更新本機，未推 GitHub。"; exit 0; fi

j(){ python3 -c "import json,sys;print(json.load(open('$SYNC'))['$1'])"; }
OWNER="$(j owner)"; REPO_N="$(j repo)"; BRANCH="$(j branch)"; TOKEN="$(j token)"
mask(){ sed -e "s/${TOKEN}/***/g" -e "s#x-access-token:[^@]*@#x-access-token:***@#g"; }
REMOTE="https://x-access-token:${TOKEN}@github.com/${OWNER}/${REPO_N}.git"

TMP="$(mktemp -d "/tmp/lava_console_push.XXXXXX")"; trap 'rm -rf "$TMP"' EXIT
git clone -q --depth 1 -b "$BRANCH" "$REMOTE" "$TMP" 2>&1 | mask
for p in "$@"; do
  [ -e "$REPO/$p" ] || { echo "  ! 略過不存在的路徑 $p"; continue; }
  mkdir -p "$TMP/$(dirname "$p")"
  rm -rf "$TMP/$p"
  cp -R "$REPO/$p" "$TMP/$p"
  ( cd "$TMP" && git add "$p" )
done
cd "$TMP"
git config user.email sync@lava.local; git config user.name lava-sync
if git diff --cached --quiet; then echo "＝ 無變更，略過推送。"; exit 0; fi
git commit -q -m "$MSG" 2>&1 | mask
push(){ git push origin "HEAD:$BRANCH" 2>&1 | mask; }
if ! push; then
  echo "… 推送被拒，fetch + rebase 後重試一次"
  git fetch -q origin "$BRANCH" 2>&1 | mask
  git rebase "origin/$BRANCH" 2>&1 | mask
  push
fi
echo "✓ 已推上 $OWNER/$REPO_N@$BRANCH：$*"
