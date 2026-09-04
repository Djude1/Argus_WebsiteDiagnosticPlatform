#!/usr/bin/env bash
# ==============================================================================
# TITAN-SEC // Automated Penetration Engine with HTML Dossier Generator
# Build: v0.3.0-BETA (x86_64)
# ==============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ts() { date "+%H:%M:%S.%3N"; }
log_recon()  { echo -e "${CYAN}[$(ts)] [RECON]${NC}  $1"; }
log_vuln()   { echo -e "${RED}[$(ts)] [VULN]${NC}   ${BOLD}$1${NC}"; }
log_audit()  { echo -e "${PURPLE}[$(ts)] [AUDIT]${NC}  $1"; }
log_safe()   { echo -e "${GREEN}[$(ts)] [SAFE]${NC}   $1"; }
log_report() { echo -e "${YELLOW}[$(ts)] [REPORT]${NC} $1"; }

REPORT_FILE="titan_audit_report_$(date +%Y%m%d_%H%M%S).html"
SCAN_TIME="$(date '+%Y-%m-%d %H:%M:%S')"

clear
echo -e "${RED}${BOLD}"
echo "  ████████╗██╗████████╗ █████╗ ███╗   ██╗    ███████╗███████╗ ██████╗ "
echo "  ╚══██╔══╝██║╚══██╔══╝██╔══██╗████╗  ██║    ██╔════╝██╔════╝██╔════╝ "
echo "     ██║   ██║   ██║   ███████║██╔██╗ ██║    ███████╗█████╗  ██║      "
echo "     ██║   ██║   ██║   ██╔══██║██║╚██╗██║    ╚════██║██╔══╝  ██║      "
echo "     ██║   ██║   ██║   ██║  ██║██║ ╚████║    ███████║███████╗╚██████╗ "
echo "     ╚═╝   ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝    ╚══════╝╚══════╝ ╚═════╝ "
echo -e "${NC}"
echo -e "${YELLOW}Target Scope:  10.142.0.0/24 (Internal Perimeter)${NC}"
echo -e "${YELLOW}Profile:       Full Spectrum Audit & Threat Dossier Generation${NC}"
echo -e "${CYAN}----------------------------------------------------------------------${NC}"
sleep 0.6

# Phase 1: 網路節點探測
log_recon "Initiating ARP broadcast across 254 subnet vectors..."
for ip in "10.142.0.12" "10.142.0.45" "10.142.0.88" "10.142.0.103" "10.142.0.210"; do
  sleep 0.15
  echo -e "  └─ Active node found: ${BOLD}${ip}${NC} (TTL=64, RTT=1.4ms)"
done
echo ""
sleep 0.4

# Phase 2: 連接埠與服務識別
log_recon "Enumerating service banners and TLS certificates..."
sleep 0.3
echo -e "  [TCP 443]  Open | Envoy/1.28.0 | TLS 1.3 (Cipher: ECDHE-RSA-AES256-GCM)"
sleep 0.2
echo -e "  [TCP 6379] Open | Redis Core Instance (Auth: Unprotected Socket)"
sleep 0.2
echo -e "  [TCP 6443] Open | Kubernetes API Server (v1.30.2-k8s)"
sleep 0.2
echo -e "  [TCP 8080] Open | Spring Boot Actuator (/env endpoint exposed)"
echo ""
sleep 0.5

# Phase 3: 漏洞比對
log_audit "Cross-referencing telemetry with Zero-Day & NVD feeds..."
sleep 0.4
log_vuln "CRITICAL: CVE-2024-38077 - Unauthenticated RCE in Routing Buffer"
sleep 0.3
log_vuln "HIGH:     CVE-2024-4577  - Argument Injection via CGI Environment"
sleep 0.3
log_safe "IMMUNE:   OpenSSL heartbeat extension integrity confirmed"
sleep 0.3
log_safe "HARDENED: SELinux namespace enforcement operational"
echo ""
sleep 0.5

# Phase 4: 模擬 Payload 驗證
log_audit "Running sandbox exploit simulations (Non-Destructive)..."
payloads=(
  "bypassing memory canary token"
  "testing blind SQL timing discrepancy"
  "injecting deserialization gadgets"
)
for p in "${payloads[@]}"; do
  echo -ne "${BLUE}[$(ts)] [EXPLOIT]${NC} ${p}... "
  sleep 0.3
  echo -e "${YELLOW}[INTERCEPTED]${NC}"
done

echo -ne "${BLUE}[$(ts)] [EXPLOIT]${NC} traversing actuator heap dump extraction... "
sleep 0.5
echo -e "${RED}${BOLD}[BREACH CONFIRMED]${NC}"
echo ""

# Phase 5: 生成假 HTML 弱點報告
log_report "Compiling cryptographic audit ledger..."
sleep 0.5
log_report "Rendering executive dashboard into HTML..."

cat << EOF > "$REPORT_FILE"
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TITAN-SEC // Penetration Audit Dossier</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #111827;
      --border: #1f2937;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --red: #ef4444;
      --amber: #f59e0b;
      --green: #10b981;
      --cyan: #06b6d4;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", monospace; }
    body { background: var(--bg); color: var(--text); padding: 32px; line-height: 1.5; }
    .container { max-width: 1080px; margin: 0 auto; }
    .header { border-bottom: 1px solid var(--border); padding-bottom: 24px; margin-bottom: 32px; display: flex; justify-content: space-between; align-items: flex-end; }
    .title { font-size: 24px; font-weight: 800; letter-spacing: 1px; color: #fff; }
    .title span { color: var(--red); }
    .meta { font-size: 13px; color: var(--muted); }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
    .badge-crit { background: rgba(239, 68, 68, 0.2); color: var(--red); border: 1px solid var(--red); }
    .badge-high { background: rgba(245, 158, 11, 0.2); color: var(--amber); border: 1px solid var(--amber); }
    .badge-safe { background: rgba(16, 185, 129, 0.2); color: var(--green); border: 1px solid var(--green); }
    
    .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }
    .card-label { font-size: 12px; color: var(--muted); text-transform: uppercase; margin-bottom: 8px; font-weight: 600; }
    .card-val { font-size: 28px; font-weight: 800; color: #fff; }
    .card-val.danger { color: var(--red); }

    .section-title { font-size: 16px; font-weight: 700; margin-bottom: 16px; color: var(--cyan); display: flex; align-items: center; gap: 8px; }
    table { width: 100%; border-collapse: collapse; background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 32px; }
    th { background: #1a2234; text-align: left; padding: 12px 16px; font-size: 12px; color: var(--muted); text-transform: uppercase; border-bottom: 1px solid var(--border); }
    td { padding: 14px 16px; font-size: 13px; border-bottom: 1px solid var(--border); color: #d1d5db; }
    tr:last-child td { border-bottom: none; }
    .host-tag { font-family: monospace; color: var(--cyan); }
    
    .remediation-box { background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 20px; }
    .remediation-box h4 { color: var(--red); margin-bottom: 8px; font-size: 14px; }
    .remediation-box ul { padding-left: 20px; font-size: 13px; color: var(--muted); }
    .remediation-box li { margin-bottom: 4px; }
    .footer { text-align: center; margin-top: 40px; font-size: 12px; color: #4b5563; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <div class="title">TITAN<span>//</span>SEC AUDIT DOSSIER</div>
        <div class="meta" style="margin-top: 6px;">Target Perimeter: 10.142.0.0/24 • Autonomous Penetration Assessment</div>
      </div>
      <div class="meta" style="text-align: right;">
        <div>Timestamp: ${SCAN_TIME}</div>
        <div>Classification: <span style="color: var(--red); font-weight: bold;">RESTRICTED / RED TEAM</span></div>
      </div>
    </div>

    <div class="stats-grid">
      <div class="card">
        <div class="card-label">Risk Severity Score</div>
        <div class="card-val danger">9.8 / 10</div>
      </div>
      <div class="card">
        <div class="card-label">Hosts Scanned</div>
        <div class="card-val">254</div>
      </div>
      <div class="card">
        <div class="card-label">Open Surface Ports</div>
        <div class="card-val">18</div>
      </div>
      <div class="card">
        <div class="card-label">Critical Exploits</div>
        <div class="card-val danger">2</div>
      </div>
    </div>

    <div class="section-title">DETECTION & VULNERABILITY LEDGER</div>
    <table>
      <thead>
        <tr>
          <th>Severity</th>
          <th>Vulnerability Identifier</th>
          <th>Affected Asset</th>
          <th>Vector / Impact</th>
          <th>Verification Status</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><span class="badge badge-crit">Critical</span></td>
          <td><strong>CVE-2024-38077</strong></td>
          <td><span class="host-tag">10.142.0.103:8080</span></td>
          <td>Unauthenticated RCE in Remote Routing Buffer</td>
          <td style="color: var(--red); font-weight: 600;">Exploited (Heap Dumped)</td>
        </tr>
        <tr>
          <td><span class="badge badge-high">High</span></td>
          <td><strong>CVE-2024-4577</strong></td>
          <td><span class="host-tag">10.142.0.45:443</span></td>
          <td>Argument Injection via Legacy CGI Wrapper</td>
          <td style="color: var(--amber);">Probe Intercepted</td>
        </tr>
        <tr>
          <td><span class="badge badge-high">High</span></td>
          <td><strong>MISCONFIG-AUTH-NONE</strong></td>
          <td><span class="host-tag">10.142.0.88:6379</span></td>
          <td>Redis In-Memory Store Binding Without Auth</td>
          <td style="color: var(--amber);">Unauthenticated Read</td>
        </tr>
        <tr>
          <td><span class="badge badge-safe">Verified</span></td>
          <td><strong>TLS-CIPHER-SUITE</strong></td>
          <td><span class="host-tag">10.142.0.12:443</span></td>
          <td>Strict Forward Secrecy & TLS 1.3 Baseline</td>
          <td style="color: var(--green);">Compliant</td>
        </tr>
      </tbody>
    </table>

    <div class="remediation-box">
      <h4>IMMEDIATE REMEDIATION PROTOCOL REQUIRED</h4>
      <ul>
        <li>Isolate node <strong>10.142.0.103</strong> from internal ingress gateway to prevent lateral pivot.</li>
        <li>Rotate cluster secrets: Spring Actuator heap dump revealed base64 Kubernetes service account tokens.</li>
        <li>Enforce strict password requirement or Unix domain sockets on Redis node <strong>10.142.0.88</strong>.</li>
      </ul>
    </div>

    <div class="footer">
      Generated automatically by TITAN-SEC v8.3.0 // End of Autonomous Security Briefing
    </div>
  </div>
</body>
</html>
EOF

sleep 0.5
echo -e "${GREEN}======================================================================${NC}"
log_report "HTML Report saved: ${BOLD}$(pwd)/${REPORT_FILE}${NC}"
echo -e "${GREEN}======================================================================${NC}"

# 若為 macOS 或有裝 xdg-open 的 Linux，可自動開啟 (預設可直接瀏覽)
if command -v open &>/dev/null; then
  open "$REPORT_FILE" 2>/dev/null &
elif command -v xdg-open &>/dev/null; then
  xdg-open "$REPORT_FILE" 2>/dev/null &
fi
