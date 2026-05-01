#!/bin/bash

# 定義HackerOne ID
H1_ID="proleader"
H1_HEADER="X-HackerOne-Research: $H1_ID"

# 檢查target.txt是否存在
if [ ! -f "target.txt" ]; then
    echo "[!] 嗶嗶~找不到target.txt請先建立它~"
    exit 1
fi

# 建立輸出目錄
mkdir -p ./results

echo "[+] 開始自動化掃描任務..."
echo "[+] 使用Header: $H1_HEADER"

# 逐行讀取目標
while IFS= read -r url || [ -n "$url" ]; do
    # 移除可能的多餘空格
    target=$(echo $url | tr -d '\r' | tr -d ' ')
    
    # 清理檔名以便儲存((移除 https:// 和符號)
    filename=$(echo $target | sed 's/[^a-zA-Z0-9]/_/g')

    echo "--------------------------------------------------"
    echo "[*] 正在處理目標: $target"
    
    # 1. 執行Katana爬蟲
    echo "[>] 嗶嗶~啟動Katana爬取路徑..."
    katana -u "$target" -H "$H1_HEADER" -jc -o "./results/katana_$filename.txt" -d 3 -silent
    echo "[V] 嗶嗶~Katana完成~結果存進->./results/katana_$filename.txt"

    # 2. 執行Dirsearch目錄爆破
    echo "[>] 嗶嗶~啟動Dirsearch掃描敏感檔案..."
    # -e 指定副檔名, -t 執行緒設為20避免過載, --format plain 方便後續讀取
    # dirsearch -u "$url" -e php,html,js,zip,bak,config -r -w /usr/share/seclists/Discovery/Web-Content/common.txt -x 404,500,502,503 --format plain -o "result.txt"
    dirsearch -u "$target" --header "$H1_HEADER" -e conf,env,bak,zip,sql,log,php,html,js,config -r 2 -w /usr/share/seclists/Discovery/Web-Content/common.txt -x 404,500,502,503 -t 20 --format plain -o "./results/dirsearch_$filename.txt"
    echo "[V] 嗶嗶~Dirsearch完成~結果放在->./results/dirsearch_$filename.txt"

done < target.txt

echo "--------------------------------------------------"
echo "[+] 嗶嗶~所有目標掃描完畢！請檢查./results資料夾~"
