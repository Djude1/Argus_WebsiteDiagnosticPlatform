# JWT 深度攻擊（jwt_tool 方法論）

tags: jwt, forge, alg confusion, kid, jku, x5u, 金鑰, 簽章, 降級

## 簽章接受度（工具 forge_jwt 可測）
- alg=none：無簽 token 被接受＝未驗簽
- HS256 弱密鑰清單：被接受＝弱密鑰（可離線全簽）
- 競改 payload 沿用原簽：被接受＝只解不驗
- exp 過去仍接受：過期不檢查

## 演算法混淆（RS256→HS256 降級）
伺服器公鑰（常可在 JWKS/公開端點拿到）當 HS256 密鑰簽——伺服器若
用配置的公鑰驗 HMAC 簽名即中招。特徵：原 token alg=RS256 且驗證邏輯
接受 HS256 重簽＝降級成立。

## kid 注入（header 的 key id 欄位）
- 路徑穿越：kid="../../../dev/null"＋alg=HS256 空/固定密鑰簽
- SQL 注入：kid 進 DB 查詢——union 控制
- 指令注入：kid 直接進系統指令（舊實現）

## jku／x5u 外控
header 帶 jku/x5u URL 指向簽章公鑰來源——改指向可控 URL（同源上傳
點或允許網域）＝自簽自驗。

## 其他
- payload 敏感欄位（密碼雜湊/個資）＝直接洩漏 finding
- 簽章爆破：短/弱 HS256 密鑰可用字典離線驗（forge_jwt 弱清單＋
  replay 驗證）
- claim 混淆：role/isAdmin/admin 欄位名猜測——decode 原 token 看
  實際欄位結構後竄改
