---
allowed-tools: Read, Bash(grep:*), Bash(python:*), Bash(docker:*), Bash(curl:*)
description: Website（Django + React）修改後的完整測試清單，含後端 API 驗證
---

## 修改前必做

```bash
cd Website

# 確認容器都在跑
docker compose ps
# 預期：backend / frontend / nginx / db 全部 Up

# 確認 Django migration 狀態乾淨（無待跑 migration）
docker compose exec backend python manage.py showmigrations | grep "\[ \]"
# 有輸出 = 有未跑 migration，需先執行 migrate
```

---

## 改了 Model / Migration

```bash
cd Website

# 1. 產生 migration
docker compose exec backend python manage.py makemigrations

# 2. 執行 migration
docker compose exec backend python manage.py migrate

# 3. 確認無殘留（應無輸出）
docker compose exec backend python manage.py showmigrations | grep "\[ \]"
```

---

## 改了 Django API（views / serializers / urls）

### JWT 取得（需要後續測試用）

```bash
TOKEN=$(curl -s -X POST http://localhost:8888/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"你的密碼"}' \
  | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>console.log(JSON.parse(d).access))")
echo "TOKEN: $TOKEN"
```

### 公開端點（不需登入，應回 200）

```bash
# 網站內容
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/api/content/site/
# APP 設定
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/api/content/app-config/
# 公告列表
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/api/content/announcements/
# 商品列表
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/api/products/
# 團隊成員
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/api/team/
```

### JWT 保護端點（未登入應回 401）

```bash
# 帳號資料
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/api/accounts/me/
# 後台帳號管理
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/api/admin/accounts/
# 後台商品管理
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/api/admin/products/
# 後台訂單
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/api/admin/orders/
# 活動日誌
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/api/admin/analytics/logs/
```
> 以上均應回 **401**。若回 200 = 權限漏洞，立刻修。

### 登入後驗證（需先取得 TOKEN）

```bash
# 取得自己的帳號資料
curl -s http://localhost:8888/api/accounts/me/ \
  -H "Authorization: Bearer $TOKEN" \
  | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{ const r=JSON.parse(d); console.log('user:', r.username, 'role:', r.role) })"

# 後台帳號列表（需 IsStaff 權限）
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/api/admin/accounts/ \
  -H "Authorization: Bearer $TOKEN"
# 預期：200
```

### 新增端點驗證清單

改完新端點後，逐項確認：
- [ ] 公開端點無認證回 200
- [ ] 需 JWT 的端點無認證回 401
- [ ] 需 superadmin 的端點用 admin 帳號回 403
- [ ] 回傳 JSON 結構符合前端 `api/client.js` 的預期欄位

---

## 改了 serializers.py

```bash
cd Website

# 進 Django shell 快速驗證 serializer 不報錯
docker compose exec backend python manage.py shell -c "
from accounts.serializers import UserSerializer
from accounts.models import CustomUser
u = CustomUser.objects.first()
if u:
    print(UserSerializer(u).data)
else:
    print('無使用者資料')
"
```

---

## 改了 permissions.py

驗證三種角色的權限邊界：

```bash
# 測試 1：未登入 → 401
curl -s -o /dev/null -w "未登入: %{http_code}\n" \
  http://localhost:8888/api/admin/accounts/

# 測試 2：一般 admin → 200（IsStaff 通過）
curl -s -o /dev/null -w "admin: %{http_code}\n" \
  http://localhost:8888/api/admin/accounts/ \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 測試 3：一般 admin 嘗試超管操作 → 403（IsAdmin 擋住）
curl -s -o /dev/null -w "admin刪帳號: %{http_code}\n" \
  -X DELETE http://localhost:8888/api/admin/accounts/1/ \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## 改了 React 元件 / 頁面

```bash
cd Website

# 確認 build 不報錯
docker compose exec frontend npm run build 2>&1 | tail -10
```

檢查 `api/client.js` 呼叫的端點是否與後端 `config/urls.py` 路由一致：
```bash
grep -rn "api\." Website/frontend/src/api/ | grep -v ".vite\|node_modules"
```

---

## 改了 nginx.conf

```bash
cd Website

# 語法檢查
docker compose exec nginx nginx -t

# 重載（不重啟容器）
docker compose exec nginx nginx -s reload
```

---

## 常見地雷

| 情況 | 症狀 | 解法 |
|------|------|------|
| model 改了沒跑 migration | 500 錯誤 | `makemigrations` + `migrate` |
| 前端 build cache 舊 | 改了沒效果 | `docker compose build --no-cache frontend` |
| nginx proxy 路徑錯 | 404 / 502 | 確認 `proxy_pass` 結尾斜線一致 |
| JWT secret 不一致 | 401 全部失敗 | 確認 `.env` 的 `SECRET_KEY` 沒變 |
| DB port 衝突 | container 啟動失敗 | `docker compose down` 再 `up` |
| 公開端點漏加 `AllowAny` | 未登入回 401 | views.py 加 `permission_classes = [AllowAny]` |
| 新增 app 忘記加 `INSTALLED_APPS` | migration 不生效 | `settings.py` 加入 app |
| serializer 少欄位 | 前端顯示 undefined | 確認 `fields` 或 `__all__` 包含前端需要的欄位 |

---

## Port 對照（Website Docker）

| Port | 服務 |
|------|------|
| 8888 | nginx 統一入口 |
| 8000 | Django backend（容器內部）|
| 3000 | React frontend（容器內部）|
| 5432 | PostgreSQL（容器內部）|

## 後端 API 路由速查

| 路徑 | 權限 | 說明 |
|------|------|------|
| `POST /api/token/` | 公開 | 取得 JWT |
| `POST /api/token/refresh/` | 公開 | 刷新 JWT |
| `GET /api/accounts/me/` | IsAuthenticated | 自己的帳號資料 |
| `GET/POST /api/admin/accounts/` | IsStaff | 帳號管理 |
| `GET/POST /api/admin/products/` | IsStaff | 商品管理 |
| `GET/POST /api/admin/orders/` | IsStaff | 訂單管理 |
| `GET /api/admin/analytics/logs/` | IsStaff | 活動日誌 |
| `GET /api/content/app-config/` | 公開 | APP 伺服器 URL |
| `GET /api/content/announcements/` | 公開 | APP 公告 |
| `POST /api/content/impact-feedback/` | 公開 | 撞擊回報 |
