# SSRF 與 Blind 偵測（無外部回呼工具時）

tags: ssrf, blind, oob, url parameter, 內網, metadata

## SSRF 常見輸入點
URL 型參數：webhook、avatar/import URL、PDF 產生器、匯入/預覽功能、
profile 網站欄位。特徵＝server 對使用者提供的 URL 發起請求。

## 無 OOB 工具時的判定法
- **回應差異 oracle**：目標 URL 換成存在/不存在埠（127.0.0.1:80 vs
  127.0.0.1:9999）比對回應狀態/長度/延遲——連線被拒 vs timeout 差異
  即內網探測 oracle
- **時間 oracle**：不存在的 IP（10.255.255.1）會 timeout、存在服務
  快速回——量測延遲差
- 錯誤訊息回顯：SSRF 失敗訊息常帶目標的回應片段或連線錯誤細節

## 內建目標清單（通用）
- localhost／127.0.0.1 各埠（80/443/8080/3000/6379/9200）
- 雲 metadata：169.254.169.254（AWS/GCP）、100.100.100.200（Aliyun）
  ——回應帶雲端憑證 JSON＝最嚴重
- 內網網段代表位址

## 繞過輸入過濾
大小寫/短碼（127.1）、十進位/八進位 IP、IPv6（::1）、
redirect 間接（允許網域上的 302）、DNS 名稱解析內網。
