#!/usr/bin/env bash
# ==============================================================================
# TITAN-RECON // Operational Host & Port Probe with Dynamic HTML Dossier
# Supports: Single IP (e.g. 192.168.1.1) or CIDR /24 (e.g. 192.168.1.0/24)
# ==============================================================================

# 終端機顏色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ts() { date "+%H:%M:%S.%3N"; }
log_info()  { echo -e "${CYAN}[$(ts)] [INFO]${NC}  $1"; }
log_host()  { echo -e "${GREEN}[$(ts)] [ALIVE]${NC} $1"; }
log_port()  { echo -e "${YELLOW}[$(ts)] [PORT]${NC}  $1"; }
log_warn()  { echo -e "${RED}[$(ts)] [ALERT]${NC} $1"; }

# 檢查必備工具
if ! command -v nc &>/dev/null; then
  echo -e "${RED}[ERROR] 需要 'nc' (netcat) 工具進行連接埠探測。請先安裝 netcat。${NC}"
  exit 1
fi

# 目標輸入處理
TARGET="${1}"
if [ -z "$TARGET" ]; then
  echo -e "${BOLD}TITAN-RECON 實用網路探測器${NC}"
  read -r -p "請輸入目標 IP 或 /24 網段 (例: 127.0.0.1 或 192.168.1.0/24): " TARGET
fi

if [ -z "$TARGET" ]; then
  echo -e "${RED}未輸入目標，程式結束。${NC}"
  exit 1
fi

REPORT_FILE="recon_report_$(date +%Y%m%d_%H%M%S).html"
START_SECONDS=$(date +%s)
SCAN_TIME="$(date '+%Y-%m-%d %H:%M:%S')"

# 欲探測的常見服務連接埠: Port:服務名稱:風險等級(Low/Medium/High/Critical)
PROBE_PORTS=(
  "21:FTP:Medium"
  "22:SSH:Low"
  "23:Telnet:Critical"
  "53:DNS:Low"
  "80:HTTP:Low"
  "443:HTTPS:Low"
  "3306:MySQL:Medium"
  "3389:RDP:High"
  "5432:PostgreSQL:Medium"
  "6379:Redis:High"
  "8080:HTTP-Alt:Low"
  "8443:HTTPS-Alt:Low"
)

# 平台相容 Ping 函式
ping_host() {
  local ip="$1"
  if [[ "$OSTYPE" == "darwin"* ]]; then
    ping -c 1 -t 1 "$ip" >/dev/null 2>&1
  else
    ping -c 1 -W 1 "$ip" >/dev/null 2>&1
  fi
}

# 連接埠探測函式 (逾時 1 秒)
probe_port() {
  local ip="$1"
  local port="$2"
  nc -z -w 1 "$ip" "$port" >/dev/null 2>&1
}

clear
echo -e "${RED}${BOLD}"
echo "  ████████╗██╗████████╗ █████╗ ███╗   ██╗    ██████╗ ███████╗ ██████╗ ██████╗ ███╗   ██╗"
echo "  ╚══██╔══╝██║╚══██╔══╝██╔══██╗████╗  ██║    ██╔══██╗██╔════╝██╔════╝██╔═══██╗████╗  ██║"
echo "     ██║   ██║   ██║   ███████║██╔██╗ ██║    ██████╔╝█████╗  ██║     ██║   ██║██╔██╗ ██║"
echo "     ██║   ██║   ██║   ██╔══██║██║╚██╗██║    ██╔══██╗██╔══╝  ██║     ██║   ██║██║╚██╗██║"
echo "     ██║   ██║   ██║   ██║  ██║██║ ╚████║    ██║  ██║███████╗╚██████╗╚██████╔╝██║ ╚████║"
echo "     ╚═╝   ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝    ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝"
echo -e "${NC}"
echo -e "${YELLOW}Target:       ${BOLD}${TARGET}${NC}"
echo -e "${YELLOW}Mode:         ICMP Ping Sweep + Netcat Socket Inspection${NC}"
echo -e "${CYAN}----------------------------------------------------------------------------------${NC}"

LIVE_HOSTS=()
TOTAL_TARGETS=0

# Phase 1: 存活主機判定
if [[ "$TARGET" =~ /24$ ]]; then
  BASE_IP="${TARGET%.*}"
  TOTAL_TARGETS=254
  log_info "偵測到 /24 網段，啟動並行 ICMP Ping 掃描 (1~254)..."
  
  TMP_LIVE=$(mktemp)
  for i in $(seq 1 254); do
    (
      IP="${BASE_IP}.${i}"
      if ping_host "$IP"; then
        echo "$IP" >> "$TMP_LIVE"
      fi
    ) &
    # 批次限制，避免過多併發進程
    if (( i % 64 == 0 )); then
      wait
    fi
  done
  wait

  while IFS= read -r host; do
    [ -n "$host" ] && LIVE_HOSTS+=("$host")
  done < "$TMP_LIVE"
  rm -f "$TMP_LIVE"
else
  TOTAL_TARGETS=1
  log_info "單一主機目標驗證中..."
  if ping_host "$TARGET"; then
    LIVE_HOSTS+=("$TARGET")
  else
    log_warn "目標主機未回應 ICMP Ping (可能離線或防火牆阻擋)，仍將嘗試進行連接埠探測。"
    LIVE_HOSTS+=("$TARGET")
  fi
fi

echo ""
log_info "主機探索完成：共發現 ${#LIVE_HOSTS[@]} 台可達目標。"
echo ""

# Phase 2: 連接埠與服務掃描 + 記錄動態數據
TOTAL_OPEN_PORTS=0
CRIT_COUNT=0
HIGH_COUNT=0
HTML_TABLE_ROWS=""

for host in "${LIVE_HOSTS[@]}"; do
  log_host "開始檢測節點: ${BOLD}${host}${NC}"
  HOST_PORTS_FOUND=0

  for entry in "${PROBE_PORTS[@]}"; do
    IFS=":" read -r port svc risk <<< "$entry"
    
    if probe_port "$host" "$port"; then
      ((TOTAL_OPEN_PORTS++))
      ((HOST_PORTS_FOUND++))
      log_port "  └─ [OPEN] Port ${port} (${svc}) - 威脅基準: ${risk}"

      # 徽章樣式匹配
      BADGE_CLASS="badge-low"
      if [ "$risk" = "Critical" ]; then
        BADGE_CLASS="badge-crit"
        ((CRIT_COUNT++))
      elif [ "$risk" = "High" ]; then
        BADGE_CLASS="badge-high"
        ((HIGH_COUNT++))
      elif [ "$risk" = "Medium" ]; then
        BADGE_CLASS="badge-med"
      fi

      HTML_TABLE_ROWS+="<tr>
        <td><span class=\"badge ${BADGE_CLASS}\">${risk}</span></td>
        <td><strong class=\"host-tag\">${host}</strong></td>
        <td>TCP / ${port}</td>
        <td>${svc}</td>
        <td style=\"color: #10b981; font-weight: 600;\">Active Listener</td>
      </tr>"
    fi
  done

  if [ "$HOST_PORTS_FOUND" -eq 0 ]; then
    echo -e "  └─ [CLEAN] 預設特徵埠皆未開放或被過濾。"
  fi
  echo ""
done

END_SECONDS=$(date +%s)
ELAPSED_TIME=$((END_SECONDS - START_SECONDS))

# 若全無開放連接埠，產出空數據行
if [ -z "$HTML_TABLE_ROWS" ]; then
  HTML_TABLE_ROWS="<tr><td colspan=\"5\" style=\"text-align: center; color: var(--muted); padding: 24px;\">未在探測節點上發現常見監聽埠（可能啟用了自訂埠號或強固型防火牆）。</td></tr>"
fi

# 計算整體風險指數 (CVSS 估值)
SEVERITY_SCORE=1.0
if [ "$CRIT_COUNT" -gt 0 ]; then
  SEVERITY_SCORE=9.4
elif [ "$HIGH_COUNT" -gt 0 ]; then
  SEVERITY_SCORE=7.6
elif [ "$TOTAL_OPEN_PORTS" -gt 0 ]; then
  SEVERITY_SCORE=4.2
fi

# Phase 3: 渲染動態 HTML 報告
log_info "正在彙整真實掃描數據並生成 HTML 報告..."

cat << EOF > "$REPORT_FILE"
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TITAN-RECON // 網路安全探測審計報告</title>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111726;
      --border: #1e293b;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --red: #ef4444;
      --amber: #f59e0b;
      --green: #10b981;
      --cyan: #06b6d4;
      --blue: #3b82f6;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }
    body { background: var(--bg); color: var(--text); padding: 32px; line-height: 1.5; }
    .container { max-width: 1100px; margin: 0 auto; }
    .header { border-bottom: 1px solid var(--border); padding-bottom: 24px; margin-bottom: 32px; display: flex; justify-content: space-between; align-items: flex-end; }
    .title { font-size: 24px; font-weight: 800; letter-spacing: 1px; color: #fff; }
    .title span { color: var(--cyan); }
    .meta { font-size: 13px; color: var(--muted); }
    
    .badge { display: inline-block; padding: 3px 10px; border-radius: 9999px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
    .badge-crit { background: rgba(239, 68, 68, 0.2); color: var(--red); border: 1px solid var(--red); }
    .badge-high { background: rgba(245, 158, 11, 0.2); color: var(--amber); border: 1px solid var(--amber); }
    .badge-med  { background: rgba(59, 130, 246, 0.2); color: var(--blue); border: 1px solid var(--blue); }
    .badge-low  { background: rgba(16, 185, 129, 0.2); color: var(--green); border: 1px solid var(--green); }
    
    .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }
    .card-label { font-size: 11px; color: var(--muted); text-transform: uppercase; margin-bottom: 8px; font-weight: 600; letter-spacing: 0.5px; }
    .card-val { font-size: 28px; font-weight: 800; color: #fff; }
    .card-val.danger { color: var(--red); }
    .card-val.warning { color: var(--amber); }
    .card-val.accent { color: var(--cyan); }

    .section-title { font-size: 15px; font-weight: 700; margin-bottom: 16px; color: var(--cyan); display: flex; align-items: center; gap: 8px; }
    table { width: 100%; border-collapse: collapse; background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 32px; }
    th { background: #162032; text-align: left; padding: 12px 16px; font-size: 12px; color: var(--muted); text-transform: uppercase; border-bottom: 1px solid var(--border); }
    td { padding: 14px 16px; font-size: 13px; border-bottom: 1px solid var(--border); color: #cbd5e1; }
    tr:last-child td { border-bottom: none; }
    .host-tag { font-family: monospace; color: var(--cyan); }

    .recommend-box { background: rgba(6, 182, 212, 0.04); border: 1px solid rgba(6, 182, 212, 0.3); border-radius: 8px; padding: 20px; }
    .recommend-box h4 { color: var(--cyan); margin-bottom: 8px; font-size: 14px; font-weight: 700; }
    .recommend-box ul { padding-left: 20px; font-size: 13px; color: var(--muted); }
    .recommend-box li { margin-bottom: 6px; }
    .footer { text-align: center; margin-top: 40px; font-size: 12px; color: #475569; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <div class="title">TITAN<span>//</span>RECON OPERATIONAL DOSSIER</div>
        <div class="meta" style="margin-top: 6px;">Target Scope: <strong>${TARGET}</strong> • Socket Verification</div>
      </div>
      <div class="meta" style="text-align: right;">
        <div>掃描時間: ${SCAN_TIME}</div>
        <div>花費秒數: ${ELAPSED_TIME}s • 探測引擎: Netcat Socket Loop</div>
      </div>
    </div>

    <div class="stats-grid">
      <div class="card">
        <div class="card-label">威脅風險估值 (CVSS)</div>
        <div class="card-val danger">${SEVERITY_SCORE} / 10</div>
      </div>
      <div class="card">
        <div class="card-label">探測範圍節點</div>
        <div class="card-val">${TOTAL_TARGETS}</div>
      </div>
      <div class="card">
        <div class="card-label">在線存活主機</div>
        <div class="card-val accent">${#LIVE_HOSTS[@]}</div>
      </div>
      <div class="card">
        <div class="card-label">開放服務連接埠</div>
        <div class="card-val warning">${TOTAL_OPEN_PORTS}</div>
      </div>
    </div>

    <div class="section-title">開放式網絡服務與監聽清單 (ACTIVE SERVICES LEDGER)</div>
    <table>
      <thead>
        <tr>
          <th>暴露層級</th>
          <th>目標節點 IP</th>
          <th>監聽埠號</th>
          <th>指紋特徵 (Service)</th>
          <th>探測狀態</th>
        </tr>
      </thead>
      <tbody>
        ${HTML_TABLE_ROWS}
      </tbody>
    </table>

    <div class="recommend-box">
      <h4>加固與審計處置建議 (HARDENING PROTOCOL)</h4>
      <ul>
        <li>若有暴露 <strong>Telnet (23)</strong> 或未加密 <strong>FTP (21)</strong>，應立刻汰換為 SSH 與 SFTP 加密傳輸通道。</li>
        <li>若資料庫連接埠（<strong>MySQL 3306、PostgreSQL 5432、Redis 6379</strong>）對外開放，請檢查 <code>bind-address</code> 是否僅綁定 <code>127.0.0.1</code> 或限制在 VPC 內部網段。</li>
        <li>生產環境建議配置主機型防火牆（如 <code>iptables</code>、<code>nftables</code> 或 <code>ufw</code>）實施 Default-Drop 策略。</li>
      </ul>
    </div>

    <div class="footer">
      Generated automatically by TITAN-RECON // Operational Infrastructure Security
    </div>
  </div>
</body>
</html>
EOF

echo -e "${GREEN}==================================================================================${NC}"
echo -e "${GREEN}[DONE] 掃描完成！報告已儲存至:${NC} ${BOLD}$(pwd)/${REPORT_FILE}${NC}"
echo -e "${GREEN}==================================================================================${NC}"

# 自動調用系統瀏覽器開啟
if command -v open &>/dev/null; then
  open "$REPORT_FILE" 2>/dev/null &
elif command -v xdg-open &>/dev/null; then
  xdg-open "$REPORT_FILE" 2>/dev/null &
fi
