#!/bin/bash

# 檢查 targets.txt 是否存在
if [ ! -f targets.txt ]; then
    echo "錯誤: 找不到 targets.txt 檔案！"
    exit 1
fi

# 建立存放結果的資料夾
mkdir -p auto_scan_results

# 開始逐行讀取目標進行掃描
while IFS= read -r url; do
    echo "--------------------------------------------------"
    echo "正在掃描目標: $url"
    echo "--------------------------------------------------"
    
    # 執行 dirsearch
    # -u: 目標網址
    # -e: 掃描 php, html, js 副檔名
    # -x: 排除 404, 403, 500 等狀態碼，讓結果更乾淨
    # --format: 輸出成純文字格式
    # -o: 將結果存到 scan_results 資料夾下，並以網域名稱命名
    
    domain=$(echo $url | awk -F[/:] '{print $4}')
    dirsearch -u "$url" -e php,html,js -w /usr/share/seclists/Discovery/Web-Content/common.txt -x 404,403,500 --format plain -o "auto_scan_results/${domain}.txt"
    #dirsearch -u "$url" -e php,html,js -x 404,403,500 --format plain -o "scan_results/${domain}.txt"
    
done < targets.txt

echo "=================================================="
echo "所有掃描已完成！結果儲存在 auto_scan_results/ 資料夾中。"
