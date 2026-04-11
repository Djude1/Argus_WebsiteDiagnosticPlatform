#!/bin/bash

export SHELL=$(which bash)
# ---Pre_Settings---
H1_ID="proleader"
H1_HEADER="X-HackerOne-Research: $H1_ID"
TARGET_FILE="targets.txt"
RESULT_DIR="./results"
MAX_PARALLEL_URLS=4 #平行掃4個不同的URL

# 建立輸出目錄
mkdir -p "$RESULT_DIR"

# 檢查檔案
if [ ! -f "$TARGET_FILE" ]; then
    echo "[!] 嗶嗶~找不到$TARGET_FILE，請先建立它嘻嘻~"
    exit 1
fi

# ---導出變數與函數給GNU Parallel使用---
export H1_HEADER RESULT_DIR
#export -f perform_full_scan

# 定義單一目標的完整掃描邏輯
perform_full_scan() {
    url=$1
    # 清理URL格式：移除空格與換行
    target=$(echo "$url" | tr -d '\r' | tr -d ' ')
    
    # 清理檔名以便儲存 (移除https://和符號)
    filename=$(echo "$target" | sed 's/[^a-zA-Z0-9]/_/g')

    echo "[*] 正在處理目標:$target"
    
    # 1.執行Katana爬蟲
    # -jc:檢查JS內容, -d 3:深度為3
    katana -u "$target" \
           -H "$H1_HEADER" \
           -jc \
           -o "$RESULT_DIR/katana_$filename.txt" \
           -d 3 -silent

    # 2.執行Dirsearch目錄爆破~Explosion~
    # -t 20: 每個網站內部20執行緒
    dirsearch -u "$target" \
              --header "$H1_HEADER" \
              -e conf,env,bak,zip,sql,log,php,html,js,config \
              -r \
              -w /usr/share/seclists/Discovery/Web-Content/common.txt \
              -x 404,500,502,503 \
              -t 20 \
              --format plain \
              -o "$RESULT_DIR/dirsearch_$filename.txt" > /dev/null 2>&1

    echo "[V] 嗶嗶~$target掃描完B！"
}

# 匯出函數
export -f perform_full_scan

# 確保子程序使用 bash
export SHELL=$(which bash)

echo "[+] 嗶嗶~開始自動化掃描任務..."
echo "[+] 使用Header:$H1_HEADER"
echo "[+] 平行限制: 同時處理$MAX_PARALLEL_URLS個目標"

# 使用GNU Parallel執行過濾後的目標清單
# 1.grep 過濾掉標籤行、註解行與空行
# 2.parallel 分發任務，並加上--env強制傳遞函數
grep -v '^#' "$TARGET_FILE" | grep -v '^\[' | grep -v '^$' | \
parallel --env perform_full_scan -j "$MAX_PARALLEL_URLS" --delay 2 --bar perform_full_scan {}

echo "---------------------------------------------------------"
echo "[+] 嗶嗶~所有目標並行掃描完畢！請檢查$RESULT_DIR資料夾~"
