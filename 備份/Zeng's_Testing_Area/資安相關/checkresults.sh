#!/bin/bash

# 設定結果目錄
RESULT_DIR="./results"

# 檢查目錄是否存在
if [ ! -d "$RESULT_DIR" ]; then
    echo "[!] 錯誤！找不到目錄：$RESULT_DIR"
    exit 1
fi

echo "[+] 嗶嗶~開始掃描$RESULT_DIR下的.txt 檔案..."
echo "[+] 嗶嗶~正在尋找狀態碼：200(OK) or 403(Forbidden)"
echo "---------------------------------------------------------"

# 使用grep進行掃描
# -r：遞迴搜尋
# -E：使用擴充正規表示法 (以便同時搜尋 200 或 403)
# --color=always：標示關鍵字顏色
# "200 |403 "：搜尋包含200或403的（前後加空格避免誤判如1200或4030）

grep -rE "200 " "$RESULT_DIR"/*.txt --color=always

echo "---------------------------------------------------------"
echo "[V] 嗶嗶~掃描完畢！"
