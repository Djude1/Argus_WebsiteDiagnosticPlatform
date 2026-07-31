# JS 庫漏洞規則庫（vendored）

`jsrepository.json` 為 [Retire.js](https://github.com/RetireJS/retire.js) 官方規則庫快照，
供 `js_library_scanner.py` 離線比對第三方 JS 庫版本→已知 CVE（OWASP A06）。

- **來源**：https://raw.githubusercontent.com/RetireJS/retire.js/master/repository/jsrepository.json
- **授權**：Apache-2.0（© Retire.js contributors），vendoring 須保留本出處與授權標註。
- **更新方式**（需要時手動重拉並 commit，無排程自動更新）：

  ```powershell
  curl -fsSL -o backend/apps/scans/security/data/jsrepository.json `
    https://raw.githubusercontent.com/RetireJS/retire.js/master/repository/jsrepository.json
  ```

---

# 後端服務 CVE DB（vendored）

`backend_services.json` 供 `service_cve_scanner.py` 離線比對後端服務（nginx / Apache / PHP）
版本→已知 CVE（OWASP A06）。結構與 `jsrepository.json` 的 vulnerabilities 區間欄位一致
（`atOrAbove` / `below` / `atOrBelow`），故比對重用 `js_library_scanner._is_vulnerable`。

- **來源**：NVD 2.0 API，過濾三產品 CPE（見 `nvd_db.py`）。
- **授權**：NVD 為美國政府 public domain；首次 vendor 前請依團隊政策再確認。
- **更新方式**（需要時手動執行；`NVD_API_KEY` 環境變數可提升速率限制）：

  ```powershell
  uv run python backend/manage.py refresh_backend_cve_db
  ```

- 轉換正確性由 `tests_nvd_db.py` 的已知答案 fixture 鎖定；首次執行請確認 NVD API 查詢格式。
