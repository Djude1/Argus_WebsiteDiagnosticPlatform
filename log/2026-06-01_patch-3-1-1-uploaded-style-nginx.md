# 2026-06-01 patch 3-1-1 uploaded style nginx

## 需求

- 使用者要求以目前上傳的較佳版 3-1-1 架構圖風格為基礎修改。
- 保留圖片字體粗細、大小與整體風格。
- 補上 Nginx。
- 將輸出結果/報告回傳重導為經過 Nginx。
- 將圖內標題由「Argus 掃描任務系統流程」改為「Argus SaaS 分層系統架構圖」。
- 直接修改指定 DOCX，不另存新檔。

## 修改

- 以 `專題文件生成/argus_3_1_1_system_flow.png` 的原有風格為底圖局部修改。
- 新增 `Nginx` 節點於 PWA 與 Django REST API 之間。
- 將流程更新為 `PWA → Nginx → Django API`。
- 將報告回傳路徑更新為 `報告/DOCX → Django API → Nginx → PWA`。
- 產出嵌入用圖片：
  - `專題文件生成/argus_3_1_1_system_flow_uploaded_style_nginx.png`
- 已直接替換並儲存：
  - `專題文件/Argus_系統手冊_第三章優化版_3-1圖組優化_Nginx_報告回傳修正版.docx`

## 驗證

- 透過 Word COM 直接替換目前開啟文件中的圖 3-1-1 並儲存原檔。
- 驗證 Word 第 385 段仍有 1 張圖片，第 386 段圖說為「圖 3-1-1　Argus SaaS 分層系統架構圖」。
- 使用 Microsoft Word COM 成功匯出 PDF，確認文件可正常輸出。
