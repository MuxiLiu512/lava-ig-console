#!/usr/bin/env bash
# create_issues.sh — 讀 github/issues.json，逐一在 repo 建立 issue（含 labels）。
# 需求：.sync.json 的 token 具 Issues: Read and write。冪等性：以標題比對，已存在則略過。
#
# 用法：bash scripts/create_issues.sh [--dry-run]
set -euo pipefail
DRY="false"; [ "${1:-}" = "--dry-run" ] && DRY="true"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SYNC="$REPO_DIR/.sync.json"; ISSUES="$REPO_DIR/github/issues.json"
[ -f "$SYNC" ] || { echo "✗ 缺 .sync.json"; exit 1; }
[ -f "$ISSUES" ] || { echo "✗ 缺 github/issues.json"; exit 1; }
j(){ python3 -c "import json;print(json.load(open('$SYNC'))['$1'])"; }
OWNER="$(j owner)"; REPO="$(j repo)"; TOKEN="$(j token)"
API="https://api.github.com"; AUTH="Authorization: Bearer $TOKEN"

# 既有 issue 標題（避免重建）
existing="$(curl -s -H "$AUTH" "$API/repos/$OWNER/$REPO/issues?state=all&per_page=100" \
  | python3 -c "import sys,json;print('\n'.join(i['title'] for i in json.load(sys.stdin)))" 2>/dev/null || true)"

count=$(python3 -c "import json;print(len(json.load(open('$ISSUES'))['issues']))")
for i in $(seq 0 $((count-1))); do
  title=$(python3 -c "import json;print(json.load(open('$ISSUES'))['issues'][$i]['title'])")
  if grep -Fxq "$title" <<<"$existing"; then echo "＝ 已存在，略過：$title"; continue; fi
  payload=$(python3 -c "
import json
it=json.load(open('$ISSUES'))['issues'][$i]
print(json.dumps({'title':it['title'],'body':it['body'],'labels':it.get('labels',[])}))
")
  if [ "$DRY" = "true" ]; then echo "（dry-run）將建立：$title"; continue; fi
  url=$(curl -s -H "$AUTH" -H "Accept: application/vnd.github+json" \
    "$API/repos/$OWNER/$REPO/issues" -d "$payload" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('html_url') or d.get('message'))")
  echo "✓ $title → $url"
done
echo "完成。"
