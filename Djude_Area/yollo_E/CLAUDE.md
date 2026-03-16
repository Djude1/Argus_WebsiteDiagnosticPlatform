# CLAUDE.md

## 工作規則（必須遵守）

### 語言規範
- 所有回覆一律使用 **繁體中文**
- 所有程式碼註釋必須使用 **繁體中文**

### 絕對要遵守
- 絕對不能洩漏任何與我相關個資
- 絕對不能洩漏任何與我相關訊息

---

## 環境隔離與安全規範

### 套件與系統環境
- 任何會影響 Python 套件或環境變數的操作（例如 `pip install`、`uv add` 等）
- 必須在 **Python 虛擬環境 (`.venv`) 或 Docker 容器** 中執行
- 禁止直接污染全域 Python 環境

### Python 開發規範
- Python 套件管理統一使用 `uv`
- 建立虛擬環境：`uv venv`
- 安裝套件：`uv add`
- 執行程式：`uv run`
---

## 專案配置架構（全域強制規範 ⭐）

### ⭐ 敏感資訊統一管理

所有涉及以下內容的資料必須集中管理：

- `.pt` 模型檔案路徑
- API Key
- 密碼
- Token
- 身份驗證資訊
- 任何機密參數

禁止：

- 在程式碼中硬編碼敏感資訊

必須：

### 使用 `.env` 作為全域敏感資訊配置

規範：

- 所有專案的敏感變數必須存放於 `.env`
- 使用 `python-dotenv` 或相同方式讀取環境變數

典型使用方式：

```python
from dotenv import load_dotenv
import os

load_dotenv()

MODEL_PATH = os.getenv("MODEL_PATH")
API_KEY = os.getenv("API_KEY")
PASSWORD = os.getenv("PASSWORD")