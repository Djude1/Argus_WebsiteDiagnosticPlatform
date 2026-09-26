# GraphQL API 安全

tags: graphql, introspection, batch, alias, overload, 內省

## 發現
常見路徑：/graphql、/api/graphql、/graphiql、/playground。
從 JS/network log 找 POST application/graphql 請求。

## 內省（三級嘗試）
1. 標準全量內省查詢（__schema 全展開）
2. 精簡查詢（WAF 擋全量時，逐 type 查）
3. 最小探測 `__schema { types { name } }`
內省開放＝完整 API 結構洩漏（finding）。

## 授權與注入
- 內省拿 schema → 找敏感 mutation/query（admin/update/delete 字樣）
- 以普通帳號 token 呼叫管理 mutation＝BFLA（函數級授權缺陷）
- 物件 id 參數改鄰近值＝BOLA/IDOR（同 REST）
- mutation 走 GET 請求＝CSRF 面
- 字串參數塞 SQL/NoSQL 探測字串（後端 resolver 常直拼）

## 過載類（DoS 面——測 1-2 次即可，勿轟）
- 別名過載：同欄位 100+ 別名
- 批查詢：一次帶多個查詢
- 深度巢狀遞迴（自引用型別）
無深度/複雜度限制＝DoS 缺陷 finding。

## 資訊洩漏
- 錯誤建議（field suggestion）洩漏欄位名
- GraphiQL/Playground 上線＝debug 面暴露
- trace/debug 模式開啟回內部細節
