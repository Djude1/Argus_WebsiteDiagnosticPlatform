# 2026-06-01 minimal 3-1-1 nginx patch

## 需求

- 使用者要求以目前上傳的原始風格圖片為基礎修改圖 3-1-1。
- 圖片字體粗細、大小、風格不要更動。
- 只補上 Nginx、輸出結果重導、標題替換，以及下方流程主軸加入 Nginx。
- 直接修改指定 DOCX，不另存新檔。

## 修改

- 以 `專題文件生成/argus_3_1_1_system_flow.png` 為底圖做最小局部修補。
- 將圖內標題改為「Argus SaaS 分層系統架構圖」。
- 在 PWA 與 Django REST API 之間加入 Nginx 節點。
- 將 PWA 與 Django API 的流程改為經過 Nginx。
- 將報告輸出回流線導向 Nginx，再回到 PWA。
- 下方流程主軸更新為包含 Nginx：
  - `User → PWA → Nginx → Django API → Redis/Celery → Playwright → 掃描器/Agent → 報告 → Nginx → PWA`
- 已直接替換並儲存：
  - `專題文件/Argus_系統手冊_第三章優化版_3-1圖組優化_Nginx_報告回傳修正版.docx`
- 產出嵌入圖片：
  - `專題文件生成/argus_3_1_1_system_flow_minimal_nginx.png`

## 驗證

- Word 第 385 段仍有 1 張圖片。
- Word 第 386 段圖說仍為「圖 3-1-1　Argus SaaS 分層系統架構圖」。
- 使用 Microsoft Word COM 成功匯出 PDF，確認文件可正常輸出。
