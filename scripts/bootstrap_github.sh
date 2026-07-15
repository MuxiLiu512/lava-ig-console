#!/usr/bin/env bash
# bootstrap_github.sh — 一鍵：建 repo（若不存在）→ 首推 → 開 Pages（/docs）。
# 需求：repo 根目錄有 .sync.json（owner/repo/branch/token；token 需 Contents+Administration 權限，
#       或改用個人帳號 classic token 具 repo 權限）。Pages 開啟需 repo Administration:write。
#
# 用法：bash scripts/bootstrap_github.sh [--private]
set -euo pipefail
PRIVATE="false"; [ "${1:-}" = "--private" ] && PRIVATE="true"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SYNC="$REPO_DIR/.sync.json"
[ -f "$SYNC" ] || { echo "✗ 缺 .sync.json（複製 .sync.json.example 並填 token）"; exit 1; }
j(){ python3 -c "import json;print(json.load(open('$SYNC'))['$1'])"; }
OWNER="$(j owner)"; REPO="$(j repo)"; BRANCH="$(j branch)"; TOKEN="$(j token)"
API="https://api.github.com"; AUTH="Authorization: Bearer $TOKEN"
mask(){ sed -e "s/${TOKEN}/***/g" -e "s#x-access-token:[^@]*@#x-access-token:***@#g"; }

echo "→ 檢查 repo $OWNER/$REPO"
code=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$API/repos/$OWNER/$REPO")
if [ "$code" = "404" ]; then
  echo "→ 建立 repo（private=$PRIVATE）"
  # 個人帳號用 /user/repos；若 OWNER 是 org 改 /orgs/$OWNER/repos
  curl -s -H "$AUTH" -H "Accept: application/vnd.github+json" \
    "$API/user/repos" -d "{\"name\":\"$REPO\",\"private\":$PRIVATE,\"description\":\"Lava IG 中介操控室\"}" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('  ✓ 建立:',d.get('full_name') or d)"
else
  echo "  ✓ repo 已存在 ($code)"
fi

echo "→ 首推 $BRANCH"
cd "$REPO_DIR"
git remote remove origin 2>/dev/null || true
git remote add origin "https://x-access-token:${TOKEN}@github.com/${OWNER}/${REPO}.git"
git branch -M "$BRANCH"
git push -u origin "$BRANCH" 2>&1 | mask

echo "→ 啟用 GitHub Pages（source=$BRANCH /docs）"
curl -s -H "$AUTH" -H "Accept: application/vnd.github+json" \
  "$API/repos/$OWNER/$REPO/pages" \
  -d "{\"source\":{\"branch\":\"$BRANCH\",\"path\":\"/docs\"}}" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  ',d.get('html_url') or d.get('message') or d)" || true

echo "✓ 完成。Pages 網址約為 https://${OWNER}.github.io/${REPO}/docs/（首次部署需 1–2 分鐘）"
echo "  私有 repo 的 Pages 需 GitHub Pro/Team。"
