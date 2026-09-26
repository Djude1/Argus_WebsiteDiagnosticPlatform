# 注入家族判定與進階（SSTi／XXE／指令／LFI）

tags: ssti, xxe, command injection, lfi, template, 模板, 指令, 路徑穿越

## SSTi（模板注入）
- 偵測序列：{{7*7}}/${7*7}/<%= 7*7 %>/#{7*7}/{{7*'7'}}——回應含
  49 或 7777777＝引擎求值成功（probe_payload_injection ssti 家族）
- 引擎指紋：${7*7}=49 且 {{7*7}} 原樣→FreeMarker；錯誤訊息格式
  （Twig/Jinja/Tech.class）各異——錯誤頁常直接報引擎名
- 進階：引擎特定物件（self/config/settings）讀敏感配置

## XXE
- XML 輸入面：SOAP、XML API、rss/import、SVG 上傳（SVG 可含 ENTITY）
- 偵測：DOCTYPE+ENTITY 讀 file://——錯誤訊息帶 parser 名/路徑即中
- 盲 XXE：參數實體外帶（無 OOB 工具時看錯誤差異）

## 指令注入
- 分隔符：; | && || `...` $(...)——回應帶 ARGUSCMDPROBE 標記即中
  （probe_payload_injection command 家族）
- 盲指令：sleep 類時間 oracle（指令執行但無回顯——比對延遲）

## LFI／路徑穿越
- 相對穿越（../）與絕對路徑（/etc/passwd、/etc/hostname）
- php://filter 讀源碼（base64 回顯）
- wrapper 家族：file://、data://、expect://
- 日誌/Session 檔案包含路徑（知道應用結構後）

## 共通判定紀律
單一 payload 中＝證據；回應僅「長度差異」無 marker＝疑點需第二發
確認再 report。
