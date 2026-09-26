# NoSQL 注入深度（MongoDB 系）

tags: nosql, mongodb, $where, $regex, blind, 盲注

## 操作子（probe_payload_injection nosql 家族已含基礎三支）
- `{"$gt": ""}`／`{"$ne": null}`：繞過相等檢查（登入/查詢）
- `{"$where": "1==1"}`：JS 條件注入（錯誤回應帶 $where＝後端直收）

## $regex 盲注（逐字元抽取資料）
`{"email": {"$regex": "^a"}}` 逐字試前綴——回應（成功/失敗、長度差）
當 oracle，可抽出任意欄位值。適用登入欄或查詢欄接受物件時。

## 進階
- `$func`（舊版 mapReduce 注入）
- `$comment`：塞入查詢註解觀察 parser 行為
- 陣列參數：`?field[]=x&field[]=y` 繞過單值假設
- JSON body 內巢狀物件注入：`{"address": {"street": {"$ne": ""}}}`

## 判定線索
- 回應錯誤帶 Mongo/BSON 字樣＝操作子直達 DB
- 500 vs 200 差異（$where 語法錯誤會炸）＝注入 oracle
