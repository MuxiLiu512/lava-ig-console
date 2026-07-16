# IG 自動發佈 — 設定教學（你做，我最後串接）

目標：PT 在 ClickUp 卡片填發佈時間 → n8n 到點自動把成品發到 IG。
IG 官方只能透過 **Instagram Graph API** 程式發文，前提是專業帳號 + FB 粉專 + Meta App。以下五步做完，把 token 給我（放 n8n 憑證），我就接。

## 步驟 1 — IG 轉「專業帳號」
IG App → 設定與隱私 → 帳號類型與工具 → **切換為專業帳號** → 選 Business（商家）或 Creator（創作者）皆可。

## 步驟 2 — 綁一個 Facebook 粉專
Graph API 發文一定要透過 FB 粉專。
- 沒有粉專就先建一個（facebook.com → 建立粉專，名稱用 Lava）。
- IG App → 設定 → 帳號中心 / 已連結帳號 → 連結該 FB 粉專。
- 確認：FB 粉專 → 設定 → 已連結的帳號 → Instagram 顯示已連結。

## 步驟 3 — 建 Meta App
[developers.facebook.com](https://developers.facebook.com) → 我的應用程式 → **建立應用程式** → 類型選「**商家 Business**」。
- 在 App 裡「新增產品」→ 加 **Instagram Graph API**（或 Instagram → API setup with Instagram login 的商家版）＋ **Facebook Login**。
- App 設定 → 基本 → 記下 **App ID / App Secret**。

## 步驟 4 — 權限 + 取得 IG Business Account ID
需要這些權限（Graph API Explorer 先用開發模式測，正式上線要送 App Review）：
```
instagram_basic, instagram_content_publish,
pages_read_engagement, pages_show_list, business_management
```
- 用 **Graph API Explorer**（App 內工具）→ 選你的 App → Generate Access Token（勾上述權限）。
- 查 IG Business Account ID：`GET /me/accounts` 拿到 Page ID → `GET /{page-id}?fields=instagram_business_account` → 得到 **IG Business Account ID**。

## 步驟 5 — 換長效 Token（60 天）
Explorer 給的是短效 token（1 小時）。換成長效 Page Access Token：
```
GET /oauth/access_token?grant_type=fb_exchange_token
  &client_id={App ID}&client_secret={App Secret}
  &fb_exchange_token={短效 token}
```
拿到 **長效 Page Access Token**（約 60 天，可自動續期）。

## 給我這三樣，我就串接
1. **長效 Page Access Token**（別貼聊天——加進 n8n 的 Header/HTTP 憑證，或放本機 `.sync.json` 的 `ig_token`）
2. **IG Business Account ID**
3. 確認成品圖有公開 URL（IG API 需要 `image_url` 是公開可讀——我會用 repo 的 raw 或 Drive 公開連結）

## 我這邊會接的（串接階段）
- **發文流程**（Graph API 兩段式）：
  - 單圖：`POST /{ig-id}/media {image_url, caption}` → 得 creation_id → `POST /{ig-id}/media_publish {creation_id}`
  - Carousel（我們是 6 張）：每張先建 `is_carousel_item` 容器 → 再建 carousel 母容器帶 children → publish
- **排程**：ClickUp 卡片加「發佈時間」欄位 → PT 填時間 → n8n 每 N 分鐘掃「已排程且時間到」的卡 → 依序發佈 → 卡片轉「已發布」＋留言。
- **護欄**：發文前最後一次確認（或 dry-run 預覽），避免誤發。

> ⚠️ Meta App Review 需要幾天審核；開發模式下可先用「你自己的帳號」測試發文，審過後才能對外穩定運作。
