# 交接資料夾

> ⚠️ 此資料夾含**真實金鑰與密碼**，已加入專案 `.gitignore`，**絕不會上傳到 GitHub**。
> 交接時請透過安全管道（加密隨身碟、私人訊息等）傳遞，不要放進任何公開位置或聊天記錄。

## 用途

Argus 專案有部分檔案因含機密或屬個人環境，不進版控（git）。
新環境 `git clone` 專案後，需要把本資料夾的檔案放回對應位置才能正常運作。

## 檔案清單與還原位置

| 檔案 | 還原到 | 用途 |
|------|--------|------|
| `.env` | 專案根目錄 | Django / Vite 設定與金鑰（SECRET_KEY、JWT、各 AI API key、Google Client ID、bootstrap superuser 帳密） |
| `GoogleCloud_ApiKey.json` | 專案根目錄 | Google Cloud service account 金鑰 |
| `client_secret_*.json` | 專案根目錄 | Google OAuth 用戶端憑證（Client ID 由此檔名萃取） |
| `settings.local.json` | `.claude/settings.local.json` | Claude Code 本機權限設定（非必要，遺失可重建） |

## 新環境還原步驟

1. `git clone` 專案。
2. 把本資料夾的 `.env`、`GoogleCloud_ApiKey.json`、`client_secret_*.json` 複製到專案根目錄。
3. 把 `settings.local.json` 複製到專案的 `.claude/settings.local.json`。
4. 依專案根目錄 `使用說明.md` 的「快速啟動」執行。

## 若 .env 遺失

參考專案根目錄 `.env.example` 範本逐項填寫，各金鑰需重新取得：

- `DJANGO_SECRET_KEY` / `JWT_SECRET_KEY`：以 `python -c "import secrets; print(secrets.token_urlsafe(64))"` 重新產生即可。
- `GOOGLE_OAUTH_CLIENT_ID`：Google Cloud Console → APIs & Services → Credentials。
- AI API keys（MiniMax / GLM / Gemini）：各服務後台。

## 維護提醒

本資料夾是副本。若日後修改了專案根目錄的 `.env` 等檔案，記得同步更新此處副本，
否則交接時會給到舊版設定。
