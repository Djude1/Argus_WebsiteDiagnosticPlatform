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
