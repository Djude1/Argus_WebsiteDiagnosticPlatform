# 後端測試加速（450 秒 → 52 秒）

**日期**：2026-10-11
**操作者**：Claude

## 變更內容
- `config/settings.py`：只在 `manage.py test` 時做兩件事：
  - 改用 `MD5PasswordHasher`。
  - 設定 `ARGUS_REPORT_CHART_DPI=72`。
- `report_render/theme.chart_dpi()`：圖表解析度改讀環境變數，預設仍是 300；`charts.py` 的 10 處 `dpi=300` 改呼叫它。
- `backend/CLAUDE.md`：新增「測試速度設定」說明。

## 原因
使用者反映包含 PDF 報告測試的這組測試耗時偏高。實測：
- 每次建立使用者都要算一次 PBKDF2 雜湊（100 萬次迭代），約 0.6 秒，幾乎每個測試都會建立使用者。
- 報告測試每次產生報告都要以 300 dpi 編碼約 10 張 PNG 圖表，這是產生報告最慢的一步。

## 影響範圍
- 只在測試時生效。正式環境、本機 runserver 與正式報告的圖表都不變。
- 報告圖片在版面中以固定寬度放置，dpi 只影響圖片清晰度，不影響版面與文字內容。

## 驗證方式
- `apps.scans`＋`apps.agent`：1409 項通過（10 項略過），耗時 448.5 秒 → 52.3 秒。
- `ruff check backend` 通過。
- 根目錄 `tests/`：唯一的錯誤是沙箱沒有 `kubectl`（`test_kali_k8s_contract`），改動前也一樣，與本次無關。
