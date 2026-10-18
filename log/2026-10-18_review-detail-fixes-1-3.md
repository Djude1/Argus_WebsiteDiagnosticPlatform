# 三站報告細讀後的細節修正（第 1–3 刀）

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者提供 juice-shop／lqll.clouda／imd.ntub 三站報告，要求逐條細讀。深讀 juice-shop 全部 35 項
資安＋內容發現後抓到數個細節判定／版面缺陷，先修低風險、明確的三項。

## 1. security.txt 的聯絡 email 不判高風險（exposure_scanner）
`.well-known/security.txt` 命中後，`detect_pii_in_text` 抓到 Contact email → PII 升級把嚴重度拉到 high
（報告自己卻寫「security.txt 本身是良好實務」，自相矛盾）。security.txt 的 email 正是檔案用途（回報窗口）。
修法：`file_type == "securitytxt"` 時，email 不計入升級門檻（`pii_for_upgrade` 扣掉 email 數）；裡頭若有
手機／身分證／卡號等其他個資、或秘鑰、或內網 IP 仍照常升級。

## 2. ZAP 英文告警中文化＋英文截斷不留殘字（zap_passive.alerts_to_findings）
- 補 `_ZH["10028"]`（Off-site Redirect／Open Redirect）中文標題與修法——原本 4.12 整張卡英文。
- 有中文對照的規則不再把 ZAP 的英文 description 附在後面（全繁中報告裡是雜訊）。
- 沒有對照的規則仍附英文，但改用 `_trim_sentence` 在句末標點截斷、超出才加「…」——原本硬切 `[:600]`
  會在字中切斷（實測把 ZAP 的 "NOTE:…" 切成孤立的「NO」殘字，出現在 4.12）。

## 3. 0.0.0.0 不算內部網路外洩（ip_context）
`/api/Users` 的 `lastLoginIp` 預設 `0.0.0.0` 被判「私有／內部網段…內部網路資訊外洩」。0.0.0.0/8 在
Python ipaddress 會被 `is_private` 判 True，但它是「未指定」空值哨兵。修法：新增 `_is_internal` 排除
`is_unspecified`；`describe_ips` 對未指定位址給「通常是空值預設，不是內部 IP 外洩」。

## 驗證
- 新增：`tests_ip_context.py`（2）、`tests_exposure_scanner` securitytxt 兩案、`tests_zap_passive`
  ZAP 中文化兩案。`apps.scans.tests_ip_context`＋`tests_exposure_scanner`＋`tests_zap_passive` 48 項通過；
  `ruff check backend` 乾淨。文件同步 `security/CLAUDE.md`。

## 尚未處理（本輪審查發現、待後續刀）
- #4 跨層去重：同端點同義但 vuln_class 不同報兩次（juice-shop 4.5 中文＝4.11 英文，同一個
  /rest/admin/application-configuration）——需謹慎設計避免誤併 IDOR/XSS。
- #5 SQLi 漏洞鏈拆兩張（4.1＋4.22 影響證明）、#6 agent「缺安全標頭」總結 vs 確定性逐條重疊。
- #7 系統性：Agent 對英文網站用英文回報 → 報告夾大段英文（4.11/4.21/4.28/4.33）；需強制中文或加翻譯層。

## 備註
juice-shop 為公開漏洞靶站、lqll/imd 為授權測試；不含機密值。修正皆為判定準確度／版面，不影響掃描範圍與授權閘門。
