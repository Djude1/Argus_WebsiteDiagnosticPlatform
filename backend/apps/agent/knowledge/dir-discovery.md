# 目錄與備份殘留發現

tags: backup, directory listing, sensitive file, git, env, 備份, 敏感檔

## 備份副檔名族（對已知路徑逐一試）
.bak、.old、.swp、~、.zip、.tar.gz、.tgz、.7z、.rar、.copy、.orig、
.txt、.save——對設定檔/原始碼路徑試（config、database、index）。

## 版本控制殘留
/.git/（config/HEAD可達＝目錄列表或 curl 到 objects）、/.svn/、
/.hg/、/.DS_Store（洩漏檔名清單）、/.env（憑證直洩）。

## 目錄列表利用
拿到 listing 後：逐一 GET 敏感項（backup、log、db、secret 字樣）；
注意非標準白名單繞過（特殊字元截斷副檔名過濾——%00、大小寫、
路徑正規化差異）。

## 其他高價值目標
robots.txt 列的路徑（被排除的常有料）、sitemap.xml、
server-status、phpinfo、actuator（Spring）/metrics、debug/console、
admin 區（配合未授權測試）、swagger/openapi JSON（API 全圖）。

## 判定
找到即 report：內容敏感（憑證/內部路徑/原始碼）或可匿名存取本身
即 finding。
