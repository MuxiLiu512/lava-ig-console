#!/usr/bin/env python3
# ig_insights.py — Phase 4 空殼：Instagram Graph API 成效自動抓取。
# 目前為介面骨架＋權限註解；接上後由排程改寫 data/metrics.json（取代人工輸入）。
#
# ── 前置需求（PLAN §8.4）─────────────────────────────────────────────
# 1. IG 需為「專業帳號（Business/Creator）」並綁定一個 Facebook 粉專。
# 2. 在 Meta for Developers 建 App，取得下列權限（App Review）：
#      instagram_basic, instagram_manage_insights, pages_read_engagement,
#      pages_show_list, business_management
# 3. 取得長期有效的 Page Access Token（60 天，可自動續期）與 IG Business Account ID。
#      token 存本機 .sync.json 或環境變數 LAVA_IG_TOKEN，絕不進 repo。
#
# ── 對應指標（IG media insights → metrics.json 欄位）─────────────────
#   reach     ← insights: reach
#   likes     ← media: like_count
#   saves     ← insights: saved
#   shares    ← insights: shares
#   comments  ← media: comments_count
#   follows   ← insights: follows（需帳號等級 insights，另 endpoint）
#
# ── 端點草圖 ────────────────────────────────────────────────────────
#   GET /{ig-user-id}/media?fields=id,caption,timestamp,permalink,like_count,comments_count
#   GET /{ig-media-id}/insights?metric=reach,saved,shares
#
# 尚未實作實際 HTTP 呼叫，避免在無 token/未過 App Review 時誤跑。
import os, sys, json

REQUIRED_SCOPES = [
    "instagram_basic", "instagram_manage_insights",
    "pages_read_engagement", "pages_show_list", "business_management",
]
METRIC_MAP = {
    "reach": ("insights", "reach"), "likes": ("media", "like_count"),
    "saves": ("insights", "saved"), "shares": ("insights", "shares"),
    "comments": ("media", "comments_count"), "follows": ("insights", "follows"),
}


def fetch_media_insights(ig_user_id, token, since=None):
    """TODO(Phase 4)：呼叫 Graph API 取回貼文與 insights，映射成 metrics.json 條目。"""
    raise NotImplementedError(
        "尚未接線。需先完成 IG 專業帳號綁定與 App Review（見檔頭權限清單）。")


def main():
    token = os.environ.get("LAVA_IG_TOKEN")
    if not token:
        print("！未設定 LAVA_IG_TOKEN，Phase 4 尚未啟用。目前成效請於操控室『成效』分頁手動輸入。")
        print("   需要的權限：" + ", ".join(REQUIRED_SCOPES))
        sys.exit(0)
    print("（骨架）已偵測到 token，但 fetch 尚未實作。")


if __name__ == "__main__":
    main()
