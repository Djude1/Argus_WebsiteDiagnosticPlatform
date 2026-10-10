"""Hermes-Agent 可呼叫的 Playwright tools。

設計原則：
- 以 OpenAI function calling 格式定義 schema，讓 MiniMax / GLM 直接相容。
- ToolExecutor 接收 async Page，將 LLM 的 tool call 轉成 Playwright 動作。
- 所有 tool 回傳 JSON-serializable dict；長字串截短，避免吃光 context。
- selector 走 Playwright 標準語法（CSS / role / text），不執行任意 JS。
- report_ux_issue 不在這裡落地，executor 只把資料回傳；loop 層負責寫入 Finding。
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from apps.scans.security.kali_contracts import redact_url_query_values

DEFAULT_ACTION_TIMEOUT_MS = 5000
MAX_TEXT_BYTES = 4000
MAX_DOM_NODES = 80
_MAX_NETWORK_LOG = 200  # 被動網路觀察上限（socket.io 高頻輪詢會快速填充）


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "點擊符合 CSS selector 的第一個元素。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "在符合 selector 的輸入元素填入文字（會清掉原內容）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["selector", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "捲動頁面：direction up/down，amount 為像素。",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "amount": {"type": "integer", "minimum": 50, "maximum": 5000},
                },
                "required": ["direction", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_visible_text",
            "description": "取得目前 viewport 內可見的純文字摘要，已截短。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dom_summary",
            "description": "取得頁面互動元素摘要（最多前 80 個，含 tag、role、可見文字）。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_requests",
            "description": (
                "列出本頁載入與操作過程中，瀏覽器實際發出的 same-origin API 請求"
                "（XHR/fetch，含 method、URL、狀態碼，最新在前）。SPA 的後端"
                " API 端點（含帶 ?query= 參數的網址）只會出現在這裡，"
                "不會出現在 DOM 連結裡。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "最多回傳幾筆（預設 20）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_html",
            "description": (
                "取得目前頁面的原始 HTML（截斷至前 8000 字元）。用於檢查"
                " HTML 註釋洩漏、hidden 欄位、inline script 內的敏感值、"
                "meta 標籤等渲染文字看不到的內容。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_storage",
            "description": (
                "列出目前瀏覽器 context 的 localStorage 鍵值與 cookies"
                "（名稱＋值長度＋屬性；值經遮罩）。用於檢查 token／敏感"
                "資料的存放位置與 cookie 旗標（HttpOnly/Secure/SameSite）。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_response_headers",
            "description": (
                "以無憑證請求 GET 一個同源 URL，回傳其回應 headers"
                "（安全標頭、CORS、Set-Cookie、伺服器指紋等）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "完整同源 URL"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_nuclei",
            "description": (
                "以 Nuclei 模板引擎對同源 URL 做快掃（CVE／misconfig／"
                "exposure／default-login 模板庫）。適合你對特定端點或技術"
                "指紋有假設時指定 tags 精準掃（如 cve、exposure、"
                "misconfig、technology），比全模板掃快。回傳命中模板的"
                "id/severity/名稱——命中即以 report_security_issue 附"
                "模板 id 與證據回報。限 GET 型探測，deep_mode 授權內。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "完整同源 URL"},
                    "tags": {
                        "type": "string",
                        "description": "逗號分隔模板 tags（選填，如 cve,misconfig）",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_and_observe",
            "description": (
                "導航到一個同源 URL（可含你組好的探測 payload），並回傳**執行層**"
                "觀察：觸發的 dialog（alert/confirm/prompt＝JS 已執行的金證據）、"
                "console 訊息、渲染後的 DOM HTML 與可見文字。這是驗證 XSS／"
                "client 端渲染問題的唯一正確方式——SPA 的 HTTP 回應幾乎都是"
                "空殼，payload 是否真的被瀏覽器執行只有這裡看得到。跨源 URL"
                "會被拒絕；dialog 會自動關閉不阻塞。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "完整同源 URL（query 參數可含 URL 編碼後的探測字串）",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "decode_jwt",
            "description": (
                "解碼一個 JWT 字串的 header 與 payload（base64，不驗簽）。"
                "用於檢查 payload 內的敏感欄位（密碼雜湊、個人資料）、"
                "alg、過期時間等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "token": {"type": "string", "description": "JWT 字串（eyJ 開頭）"},
                },
                "required": ["token"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "對目前 viewport 截圖並儲存，回傳檔案路徑。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_ux_issue",
            "description": (
                "回報一個 UX 問題；不要回報修復程式碼，只描述問題與方向。"
                "嚴重度：medium＝會讓使用者卡住或完成不了主要任務；low＝造成困惑但繞得過去；"
                "info＝只是建議。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["medium", "low", "info"],
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "remediation": {"type": "string"},
                    "selector": {"type": "string"},
                },
                "required": ["severity", "title", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_sql_injection",
            "description": (
                "對『目前站台同源、且帶 query 參數』的 URL 發動一次授權範圍內的 "
                "SQL injection 主動驗證（背後以 Kali 的 sqlmap 執行）。只在你懷疑某個帶參數的 "
                "端點（例如搜尋、商品查詢）可能存在注入時才呼叫；跨站或無參數的 URL 會被拒絕。"
                "回傳是否確認可注入；確認時系統會自動記錄為 critical 資安漏洞，你不需再 report。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要驗證的完整 URL，須與目前站台同源且含 ?參數=值",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_unauthorized_access",
            "description": (
                "以『不帶任何登入憑證』的乾淨請求重放一個同源 API 端點，驗證它是否"
                "允許未授權存取。適用在：你在網路流量（get_network_requests）看到需要"
                "登入才會觸發的端點（訂單、個人資料、後台 API），想確認匿名存取是否"
                "也拿得到資料。回傳匿名請求的狀態碼、內容類型與回應片段——**由你判斷**"
                "回傳內容是否屬於應受保護的資料；確認是漏洞時用 report_security_issue"
                "回報並附上本次觀察作為證據。跨站 URL 會被拒絕。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要驗證的完整同源 URL",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replay_request",
            "description": (
                "以『目前頁面的登入態』重放一個同源 API 請求（自動帶上瀏覽器 "
                "session 的 token／cookie）。用途：在 get_network_requests 看過某端點"
                "的原始請求後，修改內容重放——例如把 URL 中的 id 換成鄰近值測試"
                "能否讀到他人資源（IDOR），或把數量／金額欄位改成負值、極端值"
                "測試是否被接受（business logic）。method 限 GET／POST；"
                "確認漏洞時用 report_security_issue 附上回應證據。"
                "註冊／登入也建議直接以此工具打 API（比操作 UI 表單快得多）："
                "POST 註冊端點建帳號、POST 登入端點拿 token，並用 "
                "store_token_key 把回應中的 token 存進瀏覽器，之後的重放就會"
                "自動帶著登入態。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "完整同源 URL"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH"]},
                    "body": {
                        "type": "object",
                        "description": (
                            "POST 的 JSON body（選填）；仿照 network log 中"
                            "該端點原本的 body 結構修改"
                        ),
                    },
                    "store_token_key": {
                        "type": "string",
                        "description": (
                            "（選填）若預期回應 JSON 含 token（常見於登入端點），"
                            "提供 localStorage 鍵名，工具會把 token 寫入，"
                            "例如 token 或 access_token"
                        ),
                    },
                    "files": {
                        "type": "array",
                        "maxItems": 2,
                        "description": (
                            "（選填）multipart 檔案上傳——請求改以"
                            " multipart/form-data 發送，body 作為表單欄位。"
                            "每項 {field: 表單欄位名, filename: 檔名（含副檔名，"
                            "可帶繞過變體）, content: 檔案內容（純文字探測內容）, "
                            "content_type: 宣告的 MIME}"
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "filename": {"type": "string"},
                                "content": {"type": "string"},
                                "content_type": {"type": "string"},
                            },
                            "required": ["field", "filename", "content"],
                        },
                    },
                },
                "required": ["url", "method"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_payload_injection",
            "description": (
                "對一個同源端點做**家族化無害注入探測**（一次跑整組 payload），"
                "涵蓋 SQL 以外的注入面：nosql（$gt/$ne 操作子）、ssti（模板"
                " {{7*7}} 類）、xxe（XML 外部實體）、command（;echo 探測標記）、"
                "lfi（路徑穿越讀系統檔）。回傳每個 payload 的狀態碼／回應長度／"
                "命中標記（如 49＝模板求值、ARGUSCMDPROBE＝指令執行、root:＝"
                "讀到 passwd）——**由你**依命中標記判定是否成立，成立時用 "
                "report_security_issue 附證據回報。GET 給 query_param（其值會被"
                "換成各 payload），POST 給 body＋inject_field。跨站 URL 會被拒絕。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "完整同源 URL（GET 需已含要注入的 query 參數）",
                    },
                    "family": {
                        "type": "string",
                        "enum": ["nosql", "ssti", "xxe", "command", "lfi"],
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST"],
                    },
                    "query_param": {
                        "type": "string",
                        "description": "（GET）URL 中要替換值的參數名",
                    },
                    "body": {
                        "type": "object",
                        "description": "（POST）JSON body（仿 network log 原始結構）",
                    },
                    "inject_field": {
                        "type": "string",
                        "description": "（POST）body 中要塞 payload 的欄位名",
                    },
                },
                "required": ["url", "family", "method"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forge_jwt",
            "description": (
                "以給定的 payload 字典偽造 JWT（本地計算，不發請求）——"
                "JWT 攻擊標準手法（jwt_tool／PortSwigger 方法論）："
                "(1) alg=none 無簽 token（伺服器未驗簽即接受的經典缺陷）；"
                "(2) HS256 以猜測密鑰簽名——secret 留空時自動用內建常見弱密鑰"
                "清單各簽一組。回傳 token 清單，**由你**逐一以 replay_request 帶 "
                "Authorization: Bearer 打受保護端點驗證是否被接受——被接受＝"
                "簽章未驗證／弱密鑰，立即 report_security_issue。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {
                        "type": "object",
                        "description": (
                            "JWT payload 字典（仿 decode_jwt 看到的結構改欄位，"
                            "如 role/email/exp）"
                        ),
                    },
                    "alg": {
                        "type": "string",
                        "enum": ["none", "HS256"],
                    },
                    "secret": {
                        "type": "string",
                        "description": "（HS256 選填）猜測密鑰；留空＝跑內建弱密鑰清單",
                    },
                },
                "required": ["payload", "alg"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "查詢內建攻擊方法論知識庫（WSTG／PayloadsAllTheThings／"
                "jwt_tool 等通用方法論的離線摘錄，純本地不外連）。用途："
                "遇到不熟悉的漏洞類型、測試卡住需要手法點子、或想確認某類"
                "漏洞的通用測法與變體時——先查再行動。回傳最相關的數段"
                "方法論（主題＋內容）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "想查的主題，如「password reset token reuse」"
                            "或「上傳副檔名繞過」"
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": (
                "在頁面的輸入框（聊天／客服／AI 助理對話框、搜尋框、留言欄）"
                "填入文字並**真的送出**，一步完成：自動偵測輸入框（或給 "
                "selector）→填入→Enter 送出（若無新請求則嘗試送出鈕）→"
                "回撈送出後的**新 API 請求**（真實端點＋你還沒見過的流量）"
                "與**頁面新回應文字**。對話機器人／互動功能的正確第一步——"
                "只 type_text 不送出＝訊息沒發、API 不會出現在流量。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要送出的訊息文字"},
                    "selector": {
                        "type": "string",
                        "description": (
                            "（選填）輸入框 CSS selector；留空自動偵測"
                            "可見的 textarea／文字輸入框"
                        ),
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "collect_target_intel",
            "description": (
                "帳號接管情報彙整（WSTG-ATHN-09 的「答案來源推理」工具化）：對"
                "你給的數個同源公開端點（留言/評論/使用者列表/備份檔等，從"
                " network log 挑）以目前登入態 GET，全文搜索目標帳號"
                "（email／username／其前綴），命中處抽前後上下文片段彙整成"
                "單一視圖——免去逐端點人工讀回應找線索（寵物名/城市/經歷"
                " 等可推安全問題答案的個人細節）。GET only；上限 8 個 URL。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "目標帳號識別（email 或 username）",
                    },
                    "urls": {
                        "type": "array",
                        "maxItems": 8,
                        "items": {"type": "string"},
                        "description": "已觀察過的同源公開資料端點（完整 URL）",
                    },
                },
                "required": ["target", "urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_security_issue",
            "description": (
                "回報一個你在實際操作或 probe 觀察中發現的資安問題（例如未授權存取、"
                "敏感資料外洩、錯誤訊息洩漏內部資訊）。必須附上你親眼觀察到的證據"
                "（回應片段、狀態碼、畫面內容），不可以臆測。回報前自問兩個問題："
                "「攻擊者現在就能做到嗎？」「別人拿著我的證據能重現嗎？」——"
                "任一為否就不要回報。攻擊性驗證請用 "
                "probe_sql_injection / probe_unauthorized_access，不要自行組攻擊 payload。"
                "severity 為 high／critical 時必須 verified=true，且你要真的先用主動工具"
                "（replay_request／probe_payload_injection／probe_unauthorized_access／"
                "probe_sql_injection）重現確認可被利用；只是觀察、沒實際驗證就維持 medium 以下，"
                "系統會自動把未驗證的 high／critical 降為 medium。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low", "info"],
                    },
                    "verified": {
                        "type": "boolean",
                        "description": (
                            "你是否已用主動工具（replay_request／probe_*）實際重現並確認"
                            "此問題可被利用。只有 true 時 high／critical 才會保留。"
                        ),
                    },
                    "title": {"type": "string"},
                    "description": {
                        "type": "string", "description": "問題描述與為什麼是風險",
                    },
                    "evidence": {
                        "type": "string",
                        "description": "實際觀察到的證據（回應片段、截圖內容等）",
                    },
                    "remediation": {"type": "string"},
                    "url": {"type": "string", "description": "發現問題的端點 URL（選填）"},
                },
                "required": ["severity", "title", "description", "evidence"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_specialist",
            "description": (
                "（指揮官專用）派出一位專家 subagent 執行深入測試，等待其完成後"
                "回傳結果摘要（發現清單＋狀態）。你可以根據每位專家的結果決定"
                "是否追加派出其他專家。角色與職責見任務說明。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "專家角色名稱（見任務說明的可用角色清單）",
                    },
                    "brief": {
                        "type": "string",
                        "description": "給該專家的任務提示：指向你觀察到的具體線索（一到三句）",
                    },
                },
                "required": ["role", "brief"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "完成本次任務並結束。當你已經回報完所有發現或無法繼續時呼叫。",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                },
            },
        },
    },
]


# ---------------------------------------------------------------------------
# 離線知識庫（knowledge/*.md）——通用攻擊方法論，檔案隨 app 打包
# ---------------------------------------------------------------------------
_KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
_KNOWLEDGE_SECTIONS: list[dict[str, Any]] | None = None


def _tokenize(text: str) -> set[str]:
    """極輕量分詞：英文小寫單詞＋中文 2-gram。"""
    tokens = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", text)}
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.update("".join(cjk[i : i + 2]) for i in range(len(cjk) - 1))
    return tokens


def _load_knowledge() -> list[dict[str, Any]]:
    """載入並快取知識檔；每個 ## 段落＝一個可檢索單元（topic/tags/section/body）。"""
    global _KNOWLEDGE_SECTIONS
    if _KNOWLEDGE_SECTIONS is not None:
        return _KNOWLEDGE_SECTIONS
    sections: list[dict[str, Any]] = []
    if _KNOWLEDGE_DIR.is_dir():
        for md in sorted(_KNOWLEDGE_DIR.glob("*.md")):
            try:
                content = md.read_text(encoding="utf-8")
            except OSError:
                continue
            lines = content.splitlines()
            topic = lines[0].lstrip("# ").strip() if lines else md.stem
            tags = ""
            body_parts: list[str] = []
            heading = ""
            for line in lines[1:]:
                if line.startswith("tags:"):
                    tags = line
                elif line.startswith("## "):
                    if body_parts:
                        sections.append(
                            {
                                "topic": topic,
                                "section": heading,
                                "tags": tags,
                                "body": "\n".join(body_parts).strip(),
                            }
                        )
                    heading = line.lstrip("# ").strip()
                    body_parts = []
                elif heading:
                    body_parts.append(line)
            if body_parts:
                sections.append(
                    {
                        "topic": topic,
                        "section": heading,
                        "tags": tags,
                        "body": "\n".join(body_parts).strip(),
                    }
                )
    _KNOWLEDGE_SECTIONS = sections
    return sections


def _search_knowledge(query: str) -> ToolOutcome:
    """關鍵詞評分檢索（tags×3＋標題×2＋內文），回 top 3 段落。"""
    sections = _load_knowledge()
    if not sections:
        return ToolOutcome(ok=False, result={"error": "knowledge_unavailable"})
    q_tokens = _tokenize(query)
    if not q_tokens:
        return ToolOutcome(ok=False, result={"error": "empty_query"})
    scored: list[tuple[float, dict[str, Any]]] = []
    for sec in sections:
        tag_tokens = _tokenize(str(sec.get("tags", "")))
        title_tokens = _tokenize(f"{sec['topic']} {sec['section']}")
        body_tokens = _tokenize(str(sec.get("body", "")))
        score = (
            3.0 * len(q_tokens & tag_tokens)
            + 2.0 * len(q_tokens & title_tokens)
            + 1.0 * len(q_tokens & body_tokens)
        )
        if score > 0:
            scored.append((score, sec))
    scored.sort(key=lambda pair: -pair[0])
    hits = [
        {
            "topic": sec["topic"],
            "section": sec["section"],
            "content": str(sec["body"])[:1500],
        }
        for _, sec in scored[:3]
    ]
    if not hits:
        return ToolOutcome(
            ok=True,
            result={"hits": [], "hint": "換個主題詞再試（如漏洞類別英文名）"},
        )
    return ToolOutcome(ok=True, result={"hits": hits})


# ---------------------------------------------------------------------------
# Task 6：依授權模式動態組裝 tool schemas，並遮罩持久化的 tool 資料
# ---------------------------------------------------------------------------
def build_tool_schemas(
    allow_sqlmap: bool,
    orchestrator: bool = False,
    specialist_roles: dict[str, dict[str, Any]] | None = None,
    allow_form_submit: bool = True,
) -> list[dict[str, Any]]:
    """依模式組裝 tool schemas。

    - allow_sqlmap（deep_mode）：主動探測工具（probe_*／replay_request）可用
    - orchestrator：指揮官模式——只留 dispatch_specialist／finish／
      report_security_issue（調度職責，不親自測試；specialist 不帶
      dispatch，防無限遞迴）
    - specialist_roles：角色目錄（name → {desc, when, ...}）。指揮官模式
      會把 role enum 與「何時派用」說明動態填入 dispatch_specialist 的
      schema——這是指揮官「知道自己手中有什麼」的機制（hermes-agent 的
      能力目錄化概念）
    回傳獨立深拷貝，避免共用 mutable schema 被意外修改。
    """
    deep_only = {
        "probe_sql_injection",
        "probe_unauthorized_access",
        "replay_request",
        "run_nuclei",
        "navigate_and_observe",
        "probe_payload_injection",
        "forge_jwt",
        "collect_target_intel",
    }
    if orchestrator:
        keep = {"dispatch_specialist", "finish", "report_security_issue"}
        schemas = [
            copy.deepcopy(s)
            for s in TOOL_SCHEMAS
            if s["function"]["name"] in keep
        ]
        if specialist_roles:
            role_names = sorted(specialist_roles.keys())
            catalog = "\n".join(
                f"- {name}: {defn.get('desc', '')}（派用時機：{defn.get('when', '')}）"
                for name, defn in specialist_roles.items()
            )
            for schema in schemas:
                if schema["function"]["name"] == "dispatch_specialist":
                    schema["function"]["parameters"]["properties"]["role"] = {
                        "type": "string",
                        "enum": role_names,
                        "description": f"可用專家角色：\n{catalog}",
                    }
        return schemas
    hidden = deep_only | {"dispatch_specialist"}
    # 未通過網域驗證的被動 UX 測試：拿掉會實際送出表單／訊息的 send_message，
    # agent 只能填入與觀察，不會在他人網站留下測試資料（提示詞也一併要求不送出）。
    if not allow_form_submit:
        hidden = hidden | {"send_message"}
    return [
        copy.deepcopy(schema)
        for schema in TOOL_SCHEMAS
        if allow_sqlmap or schema["function"]["name"] not in hidden
    ]


def redact_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """遮罩即將持久化到 AgentStep 的 tool arguments。

    probe_sql_injection 的 url 參數值可能含敏感 query value（搜尋關鍵字、ID），
    一律經 redact_url_query_values 遮罩；其他 tool 的參數原樣回傳（淺拷貝）。
    """
    clean = dict(arguments or {})
    if (
        tool_name
        in {
            "probe_sql_injection",
            "probe_unauthorized_access",
            "replay_request",
            "navigate_and_observe",
            "probe_payload_injection",
            "collect_target_intel",
        }
        and "url" in clean
    ):
        clean["url"] = redact_url_query_values(str(clean["url"]))
    if tool_name == "collect_target_intel" and isinstance(clean.get("urls"), list):
        clean["urls"] = [
            redact_url_query_values(str(u)) for u in clean["urls"] if u
        ][:8]
    # multipart 檔案內容屬探測 payload，持久化只留描述性欄位＋內容長度
    if tool_name == "replay_request" and isinstance(clean.get("files"), list):
        clean["files"] = [
            {
                "field": f.get("field"),
                "filename": f.get("filename"),
                "content_type": f.get("content_type"),
                "content_length": len(str(f.get("content") or "")),
            }
            for f in clean["files"]
            if isinstance(f, dict)
        ]
    return clean


def redact_tool_result(tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
    """遮罩即將持久化到 AgentStep 的 tool result。

    probe_sql_injection 的 result 只保留 confirmed / blocked / error / correlation_id，
    移除 target URL 與任何額外欄位（note 等），避免 raw URL 或中介資料外洩。
    """
    if tool_name == "get_network_requests":
        raw = result or {}
        return {
            "total_logged": raw.get("total_logged", 0),
            "requests": [
                {
                    **req,
                    "url": redact_url_query_values(str(req.get("url", ""))),
                }
                for req in raw.get("requests", [])
                if isinstance(req, dict)
            ],
        }
    if tool_name in {"probe_unauthorized_access", "replay_request"}:
        raw = result or {}
        safe: dict[str, Any] = {
            "status": raw.get("status"),
            "content_type": raw.get("content_type"),
            "body_length": raw.get("body_length"),
        }
        if raw.get("body_snippet"):
            safe["body_snippet"] = redact_url_query_values(str(raw["body_snippet"]))
        if raw.get("blocked"):
            safe["blocked"] = raw["blocked"]
        if raw.get("error"):
            safe["error"] = raw["error"]
        if raw.get("authenticated") is not None:
            safe["authenticated"] = raw.get("authenticated")
        if raw.get("token_stored") is not None:
            safe["token_stored"] = raw.get("token_stored")
        return safe
    if tool_name == "navigate_and_observe":
        raw = result or {}
        safe_nav: dict[str, Any] = {"status": raw.get("status")}
        if raw.get("url_after"):
            safe_nav["url_after"] = redact_url_query_values(str(raw["url_after"]))
        safe_nav["dialogs"] = [
            d for d in raw.get("dialogs", []) if isinstance(d, dict)
        ][:10]
        safe_nav["console"] = [
            c for c in raw.get("console", []) if isinstance(c, dict)
        ][:10]
        if raw.get("rendered_html"):
            safe_nav["rendered_html"] = redact_url_query_values(
                str(raw["rendered_html"])
            )[:2000]
        if raw.get("visible_text"):
            safe_nav["visible_text"] = redact_url_query_values(
                str(raw["visible_text"])
            )[:1500]
        if raw.get("error"):
            safe_nav["error"] = raw["error"]
        return safe_nav
    if tool_name == "probe_payload_injection":
        raw = result or {}
        safe_probe: dict[str, Any] = {"family": raw.get("family")}
        if isinstance(raw.get("baseline"), dict):
            safe_probe["baseline"] = {
                "status": raw["baseline"].get("status"),
                "body_length": raw["baseline"].get("body_length"),
            }
        safe_probe["results"] = [
            {
                k: item.get(k)
                for k in ("kind", "status", "body_length", "markers_hit", "error")
                if item.get(k) is not None
            }
            for item in raw.get("results", [])
            if isinstance(item, dict)
        ]
        if raw.get("error"):
            safe_probe["error"] = raw["error"]
        return safe_probe
    if tool_name != "probe_sql_injection":
        return dict(result or {})
    raw = result or {}
    safe: dict[str, Any] = {"confirmed": bool(raw.get("confirmed"))}
    if raw.get("blocked"):
        safe["blocked"] = raw["blocked"]
    if raw.get("error"):
        safe["error"] = raw["error"]
    if raw.get("correlation_id"):
        safe["correlation_id"] = raw["correlation_id"]
    return safe


# 家族化注入 payload（無害驗證導向；屬工具配備——payload/字典是給 agent
# 的工具，非目標特定答案）。markers＝回應文本出現且 baseline 未出現才算命中
_PAYLOAD_FAMILIES: dict[str, list[dict[str, Any]]] = {
    "nosql": [
        {"kind": "gt-empty", "payload": '{"$gt": ""}', "markers": ["MongoError", "BSON"]},
        {"kind": "ne-null", "payload": '{"$ne": null}', "markers": ["MongoError", "BSON"]},
        {
            "kind": "where-true",
            "payload": '{"$where": "1==1"}',
            "markers": ["MongoError", "$where"],
        },
    ],
    "ssti": [
        {"kind": "mustache", "payload": "{{7*7}}", "markers": ["49"]},
        {"kind": "dollar-brace", "payload": "${7*7}", "markers": ["49"]},
        {"kind": "erb", "payload": "<%= 7*7 %>", "markers": ["49"]},
        {"kind": "hash-brace", "payload": "#{7*7}", "markers": ["49"]},
    ],
    "xxe": [
        {
            "kind": "entity-file",
            "payload": (
                '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM '
                '"file:///etc/hostname">]><r>&x;</r>'
            ),
            "markers": ["SAXParseException", "lxml", "XML parser error"],
        },
    ],
    "command": [
        {"kind": "semicolon", "payload": ";echo ARGUSCMDPROBE", "markers": ["ARGUSCMDPROBE"]},
        {"kind": "pipe", "payload": "|echo ARGUSCMDPROBE", "markers": ["ARGUSCMDPROBE"]},
        {"kind": "backtick", "payload": "`echo ARGUSCMDPROBE`", "markers": ["ARGUSCMDPROBE"]},
        {"kind": "and-chain", "payload": "&&echo ARGUSCMDPROBE", "markers": ["ARGUSCMDPROBE"]},
    ],
    "lfi": [
        {"kind": "dotdot-passwd", "payload": "../../../../etc/passwd", "markers": ["root:"]},
        {"kind": "abs-passwd", "payload": "/etc/passwd", "markers": ["root:"]},
        {
            "kind": "filter-wrapper",
            "payload": "php://filter/convert.base64-encode/resource=index",
            "markers": ["PD9", "PGh0"],
        },
    ],
}


# JWT 偽造用常見弱密鑰清單（jwt_tool/rockyou 精選——工具配備非答案）
_WEAK_JWT_SECRETS = [
    "secret", "key", "jwt_secret", "password", "changeme",
    "123456", "jwt", "mysecret", "secretkey", "token_secret",
]


@dataclass
class ToolOutcome:
    """單一 tool 執行結果。"""

    ok: bool
    result: dict[str, Any]
    finish: bool = False  # finish/error 達成終止條件
    issue: dict[str, Any] | None = None  # report_ux_issue 的 payload
    security_finding: dict[str, Any] | None = None  # probe_sql_injection 確認後的 security finding


def _truncate(text: str, limit: int = MAX_TEXT_BYTES) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"...[truncated {len(text) - limit} chars]"


class ToolExecutor:
    """把 LLM 的 tool call 轉成 Playwright 動作。

    傳入 page 必須是 async Playwright Page；screenshot_dir 用於存截圖。
    """

    def __init__(
        self,
        page: Page,
        screenshot_dir: str,
        action_timeout_ms: int = DEFAULT_ACTION_TIMEOUT_MS,
        scan_job=None,
        specialist_dispatcher=None,
    ):
        self.page = page
        self.screenshot_dir = screenshot_dir
        self.action_timeout_ms = action_timeout_ms
        # probe_sql_injection 需要 scan_job.id / origin（同源檢查 + 授權鎖）
        self.scan_job = scan_job
        # 指揮官模式：dispatch_specialist tool 的實作由 runner 注入
        # （async fn(role, brief) -> dict 摘要）；specialist 自身不帶（防遞迴）
        self.specialist_dispatcher = specialist_dispatcher
        self._screenshot_counter = 0
        # 被動網路觀察：SPA 的 API 端點只存在於真實流量，agent 靠這個「看到」
        # 頁面自己發出的 XHR/fetch（不發任何新請求）。
        self._network_log: list[dict[str, Any]] = []
        # 主動驗證紀錄：成功呼叫過的主動工具名稱（replay_request／probe_*／run_nuclei）。
        # report_security_issue 的 high／critical 只有在這裡非空（agent 真的用工具驗證過）
        # 且 verified=true 時才保留，否則降 medium——不需 Kali，但擋 AI 純臆測自評高風險。
        self._active_confirmations: set[str] = set()
        if scan_job is not None:
            self.page.on("response", self._on_network_response)

    def _on_network_response(self, response) -> None:
        """收集 same-origin XHR/fetch 進 network log；任何例外靜默忽略。"""
        try:
            if response.request.resource_type not in {"xhr", "fetch"}:
                return
            origin = getattr(self.scan_job, "origin", "") or ""
            req_url = response.url or ""
            if urlsplit(origin).hostname != urlsplit(req_url).hostname:
                return
            if len(self._network_log) >= _MAX_NETWORK_LOG:
                self._network_log.pop(0)
            self._network_log.append(
                {
                    "method": response.request.method,
                    "url": req_url,
                    "status": response.status,
                }
            )
        except Exception:
            pass

    def _track_verification(self, name: str, outcome: ToolOutcome) -> ToolOutcome:
        """主動工具成功時記錄：之後 report_security_issue 才可破 medium 封頂。"""
        if outcome.ok:
            self._active_confirmations.add(name)
        return outcome

    async def run(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        try:
            if name == "click":
                return await self._click(args.get("selector", ""))
            if name == "type_text":
                return await self._type_text(args.get("selector", ""), args.get("text", ""))
            if name == "scroll":
                return await self._scroll(
                    args.get("direction", "down"), int(args.get("amount", 500))
                )
            if name == "get_visible_text":
                return await self._get_visible_text()
            if name == "get_dom_summary":
                return await self._get_dom_summary()
            if name == "get_network_requests":
                return self._get_network_requests(args)
            if name == "get_page_html":
                return await self._get_page_html()
            if name == "get_storage":
                return await self._get_storage()
            if name == "get_response_headers":
                return await self._get_response_headers(args.get("url", ""))
            if name == "decode_jwt":
                return self._decode_jwt(args.get("token", ""))
            if name == "search_knowledge":
                return _search_knowledge(str(args.get("query", "")))
            if name == "forge_jwt":
                if not (
                    self.scan_job is not None
                    and self.scan_job.scan_mode == self.scan_job.ScanMode.ACTIVE
                    and self.scan_job.active_testing_authorized
                ):
                    return ToolOutcome(ok=False, result={"error": "not_authorized_mode"})
                return self._forge_jwt(
                    args.get("payload") or {},
                    str(args.get("alg", "none")),
                    str(args.get("secret", "")),
                )
            if name == "run_nuclei":
                return self._track_verification(
                    name, await self._run_nuclei(args.get("url", ""), args.get("tags", ""))
                )
            if name == "take_screenshot":
                return await self._take_screenshot()
            if name == "send_message":
                return await self._send_message(
                    str(args.get("text", "")), str(args.get("selector", ""))
                )
            if name == "collect_target_intel":
                return await self._collect_target_intel(
                    str(args.get("target", "")),
                    [str(u) for u in (args.get("urls") or [])][:8],
                )
            if name == "navigate_and_observe":
                return await self._navigate_and_observe(args.get("url", ""))
            if name == "probe_payload_injection":
                return self._track_verification(name, await self._probe_payload_injection(
                    args.get("url", ""),
                    str(args.get("family", "")),
                    str(args.get("method", "GET")).upper(),
                    str(args.get("query_param", "")),
                    args.get("body"),
                    str(args.get("inject_field", "")),
                ))
            if name == "report_ux_issue":
                return self._report_ux_issue(args)
            if name == "probe_sql_injection":
                return self._track_verification(
                    name, await self._probe_sql_injection(args.get("url", ""))
                )
            if name == "probe_unauthorized_access":
                return self._track_verification(
                    name, await self._probe_unauthorized_access(args.get("url", ""))
                )
            if name == "replay_request":
                return self._track_verification(name, await self._replay_request(
                    args.get("url", ""),
                    args.get("method", "GET"),
                    args.get("body"),
                    args.get("store_token_key", ""),
                    args.get("files"),
                ))
            if name == "report_security_issue":
                return self._report_security_issue(args)
            if name == "dispatch_specialist":
                if self.specialist_dispatcher is None:
                    return ToolOutcome(
                        ok=False, result={"error": "dispatcher_not_available"}
                    )
                outcome_data = await self.specialist_dispatcher(
                    str(args.get("role", "")), str(args.get("brief", ""))
                )
                return ToolOutcome(ok=bool(outcome_data), result=outcome_data)
            if name == "finish":
                return ToolOutcome(
                    ok=True,
                    result={"summary": str(args.get("summary", ""))[:500]},
                    finish=True,
                )
            return ToolOutcome(ok=False, result={"error": f"unknown_tool:{name}"})
        except PlaywrightTimeoutError as exc:
            return ToolOutcome(ok=False, result={"error": "timeout", "detail": str(exc)[:200]})
        except Exception as exc:
            return ToolOutcome(
                ok=False,
                result={"error": exc.__class__.__name__, "detail": str(exc)[:200]},
            )

    async def _click(self, selector: str) -> ToolOutcome:
        if not selector:
            return ToolOutcome(ok=False, result={"error": "empty_selector"})
        loc = self.page.locator(selector).first
        await loc.click(timeout=self.action_timeout_ms)
        await self.page.wait_for_load_state("domcontentloaded", timeout=self.action_timeout_ms)
        url = self.page.url
        return ToolOutcome(ok=True, result={"clicked": selector, "url_after": url})

    async def _type_text(self, selector: str, text: str) -> ToolOutcome:
        if not selector:
            return ToolOutcome(ok=False, result={"error": "empty_selector"})
        loc = self.page.locator(selector).first
        await loc.fill(text, timeout=self.action_timeout_ms)
        return ToolOutcome(ok=True, result={"typed_into": selector, "length": len(text)})

    async def _scroll(self, direction: str, amount: int) -> ToolOutcome:
        delta = amount if direction == "down" else -amount
        await self.page.evaluate("(d) => window.scrollBy(0, d)", delta)
        await asyncio.sleep(0.2)
        return ToolOutcome(ok=True, result={"scrolled": delta})

    async def _get_visible_text(self) -> ToolOutcome:
        text = await self.page.evaluate(
            "() => document.body && document.body.innerText ? document.body.innerText : ''"
        )
        return ToolOutcome(ok=True, result={"text": _truncate(str(text))})

    def _get_network_requests(self, args: dict[str, Any]) -> ToolOutcome:
        """回傳被動收集的 same-origin API 請求（最新在前）。"""
        try:
            limit = max(1, min(int(args.get("limit", 20)), 50))
        except (TypeError, ValueError):
            limit = 20
        recent = list(reversed(self._network_log))[:limit]
        return ToolOutcome(
            ok=True, result={"requests": recent, "total_logged": len(self._network_log)}
        )

    async def _get_page_html(self) -> ToolOutcome:
        """原始 HTML（截斷）：注釋洩漏／hidden 欄位／inline 敏感值。"""
        try:
            html = await self.page.content()
        except Exception as exc:  # noqa: BLE001
            return ToolOutcome(ok=False, result={"error": exc.__class__.__name__})
        return ToolOutcome(ok=True, result={"html": str(html)[:8000]})

    async def _get_storage(self) -> ToolOutcome:
        """localStorage＋cookies 盤點（值遮罩為長度，不外洩內容）。"""
        try:
            entries = await self.page.evaluate(
                "() => Object.entries(localStorage).map(([k, v]) =>"
                " ({key: k, length: (v || '').length}))"
            )
        except Exception:  # noqa: BLE001
            entries = []
        try:
            cookies = await self.page.context.cookies()
        except Exception:  # noqa: BLE001
            cookies = []
        safe_cookies = [
            {
                "name": c.get("name", ""),
                "length": len(str(c.get("value", ""))),
                "httponly": bool(c.get("httpOnly")),
                "secure": bool(c.get("secure")),
                "samesite": c.get("sameSite", ""),
            }
            for c in cookies
        ]
        return ToolOutcome(
            ok=True, result={"localStorage": entries, "cookies": safe_cookies}
        )

    async def _get_response_headers(self, url: str) -> ToolOutcome:
        """匿名 GET 同源 URL，回傳回應 headers（安全標頭／指紋檢查用）。"""
        from urllib.parse import urlparse

        if self.scan_job is not None:
            parsed = urlparse(url or "")
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return ToolOutcome(ok=False, result={"error": "invalid_url"})
            target_origin = f"{parsed.scheme}://{parsed.hostname}"
            if parsed.port:
                target_origin = f"{target_origin}:{parsed.port}"
            if target_origin != self.scan_job.origin:
                return ToolOutcome(ok=False, result={"error": "cross_origin_forbidden"})

        import httpx

        def _fetch() -> dict[str, Any]:
            with httpx.Client(
                headers={"User-Agent": settings.ARGUS_SCANNER_USER_AGENT},
                timeout=10.0,
                follow_redirects=False,
            ) as client:
                r = client.get(url)
            return {"status": r.status_code, "headers": dict(r.headers)}

        try:
            observation = await asyncio.to_thread(_fetch)
        except Exception as exc:  # noqa: BLE001
            return ToolOutcome(
                ok=False, result={"error": f"request_failed:{exc.__class__.__name__}"}
            )
        return ToolOutcome(ok=True, result=observation)

    async def _run_nuclei(self, url: str, tags: str) -> ToolOutcome:
        """agent 自主的 Nuclei 指定模板快掃（worker 本機 binary）。

        與 pipeline 的 KEV 模板集（只掃網站根網址）互補：agent 對特定端點／技術指紋有
        假設時，帶 tags 精準掃（120s 上限）。gating＝deep_mode＋同源，
        與 replay_request 同邊界；JSONL 摘要回傳（template id/severity/
        name），命中由 agent report。
        """
        from urllib.parse import urlparse

        from apps.scans.models import ScanJob

        if not (
            self.scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
            and self.scan_job.active_testing_authorized
        ):
            return ToolOutcome(ok=False, result={"error": "not_authorized_mode"})
        parsed = urlparse(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ToolOutcome(ok=False, result={"error": "invalid_url"})
        target_origin = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            target_origin = f"{target_origin}:{parsed.port}"
        if target_origin != self.scan_job.origin:
            return ToolOutcome(
                ok=False,
                result={"error": "cross_origin_forbidden"},
            )

        import subprocess

        cmd = [
            "nuclei", "-u", url, "-j", "-silent", "-no-stdin", "-duc",
            # 與 pipeline 用同一份鎖定版本的模板（image 內沒有預設模板目錄）
            "-t", settings.ARGUS_NUCLEI_TEMPLATES_DIR,
            "-ni", "-dr", "-or",
            "-H", f"User-Agent: {settings.ARGUS_SCANNER_USER_AGENT}",
            "-timeout", "8", "-rl", "5", "-c", "5",
            "-severity", "critical,high,medium",
            "-etags", "dos,fuzz,creds-stuffing,token-spray",
        ]
        if tags:
            cmd += ["-tags", ",".join(t.strip() for t in tags.split(",") if t.strip())]

        def _scan() -> list[dict[str, Any]]:
            try:
                proc = subprocess.run(  # noqa: S603 — list 形式＋固定參數
                    cmd, capture_output=True, text=True, timeout=120,
                )
            except subprocess.TimeoutExpired:
                return [{"error": "timeout"}]
            hits = []
            for line in (proc.stdout or "").splitlines():
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                info = rec.get("info") or {}
                hits.append({
                    "template_id": rec.get("template-id") or rec.get("templateID", ""),
                    "severity": info.get("severity", ""),
                    "name": info.get("name", ""),
                    "type": rec.get("type", ""),
                })
            return hits

        try:
            hits = await asyncio.to_thread(_scan)
        except Exception as exc:  # noqa: BLE001
            return ToolOutcome(
                ok=False, result={"error": f"scan_failed:{exc.__class__.__name__}"}
            )
        return ToolOutcome(ok=True, result={"hits": hits[:20], "total": len(hits)})

    def _decode_jwt(self, token: str) -> ToolOutcome:
        """解 JWT header/payload（base64；不驗簽）。token 不回傳不持久化。"""
        import base64

        parts = (token or "").split(".")
        if len(parts) < 2:
            return ToolOutcome(ok=False, result={"error": "not_a_jwt"})

        def _b64(seg: str) -> dict[str, Any]:
            pad = "=" * (-len(seg) % 4)
            try:
                decoded = base64.urlsafe_b64decode(seg + pad).decode("utf-8", "ignore")
                return json.loads(decoded) if decoded else {}
            except (ValueError, json.JSONDecodeError):
                return {"_raw": decoded[:200] if decoded else ""}

        return ToolOutcome(
            ok=True, result={"header": _b64(parts[0]), "payload": _b64(parts[1])}
        )

    async def _get_dom_summary(self) -> ToolOutcome:
        # 注意：JS 模板內 .slice(0, 60) 那行因 JSON 結構需保持單行；用 noqa 略過 ruff 行長檢查
        script = (
            "() => {\n"
            "  const out = [];\n"
            "  const tags = ['a', 'button', 'input', 'select', 'textarea', 'form', 'nav'];\n"
            "  for (const tag of tags) {\n"
            "    const els = document.querySelectorAll(tag);\n"
            f"    for (let i = 0; i < els.length && out.length < {MAX_DOM_NODES}; i++) {{\n"
            "      const el = els[i];\n"
            "      const rect = el.getBoundingClientRect();\n"
            "      if (rect.width === 0 || rect.height === 0) continue;\n"
            "      out.push({\n"
            "        tag,\n"
            "        role: el.getAttribute('role') || '',\n"
            "        name: (el.getAttribute('aria-label') || el.getAttribute('placeholder')"
            " || (el.innerText || '').slice(0, 60)).trim(),\n"
            "        href: el.getAttribute('href') || '',\n"
            "        id: el.id || '',\n"
            "      });\n"
            "    }\n"
            "  }\n"
            "  return out;\n"
            "}"
        )
        nodes = await self.page.evaluate(script)
        return ToolOutcome(ok=True, result={"nodes": nodes[:MAX_DOM_NODES]})

    async def _navigate_and_observe(self, url: str) -> ToolOutcome:
        """同源導航＋執行層觀察閉環（XSS／client 端渲染驗證金標準）。

        安全約束：
        - runtime 同源再驗（比對 scan_job.origin）＋deep_mode 再驗；context
          route 的主文件同源攔截仍在（雙保險），不繞過既有邊界。
        - 只導航（GET），不執行任意 JS；dialog 自動 dismiss，不阻塞迴圈。
        - 觀察（dialogs／console／渲染 DOM）回給 LLM 判定，維持
          「工具觀察、agent 判定、report 附證據」契約。
        """
        if self.scan_job is None:
            return ToolOutcome(ok=False, result={"error": "no_scan_context"})
        from urllib.parse import urlparse

        from apps.scans.models import ScanJob

        if not (
            self.scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
            and self.scan_job.active_testing_authorized
        ):
            return ToolOutcome(ok=False, result={"error": "not_authorized_mode"})

        parsed = urlparse(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ToolOutcome(ok=False, result={"error": "invalid_url"})
        target_origin = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            target_origin = f"{target_origin}:{parsed.port}"
        if target_origin != self.scan_job.origin:
            return ToolOutcome(
                ok=False,
                result={"error": "cross_origin_forbidden", "allowed_origin": self.scan_job.origin},
            )

        dialogs: list[dict[str, Any]] = []
        console_msgs: list[dict[str, Any]] = []

        def _on_dialog(dialog) -> None:
            # 收集後立即 dismiss；非同步關閉避免阻塞 page 事件迴圈
            if len(dialogs) < 10:
                dialogs.append(
                    {"type": dialog.type, "message": str(dialog.message or "")[:200]}
                )
            asyncio.ensure_future(dialog.dismiss())

        def _on_console(msg) -> None:
            if len(console_msgs) < 20:
                console_msgs.append(
                    {"type": msg.type, "text": str(msg.text or "")[:200]}
                )

        self.page.on("dialog", _on_dialog)
        self.page.on("console", _on_console)
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            # SPA 渲染與延遲觸發的 payload（iframe onload 等）留緩衝
            await asyncio.sleep(1.0)
            html = await self.page.content()
            visible = await self.page.evaluate(
                "() => document.body && document.body.innerText"
                " ? document.body.innerText.slice(0, 1500) : ''"
            )
        except PlaywrightTimeoutError:
            return ToolOutcome(
                ok=False, result={"error": "timeout", "dialogs": dialogs}
            )
        finally:
            try:
                self.page.remove_listener("dialog", _on_dialog)
                self.page.remove_listener("console", _on_console)
            except Exception:  # noqa: BLE001 — mock/已關閉頁面下清理失敗可容忍
                pass
        return ToolOutcome(
            ok=True,
            result={
                "status": "loaded",
                "url_after": self.page.url,
                "dialogs": dialogs,
                "console": console_msgs,
                "rendered_html": str(html)[:4000],
                "visible_text": _truncate(str(visible), 1500),
            },
        )

    async def _session_credentials(self) -> tuple[str, list[dict[str, Any]]]:
        """抽瀏覽器當前登入態（localStorage token＋cookies），重放/注入共用。"""
        try:
            token = await self.page.evaluate(
                "() => { const keys = ['token','jwt','access_token','auth_token','id_token'];"
                " for (const k of keys) { const v = localStorage.getItem(k);"
                " if (v) return v.replace(/^\"|\"$/g, ''); } return ''; }"
            )
        except Exception:  # noqa: BLE001
            token = ""
        try:
            cookies = await self.page.context.cookies()
        except Exception:  # noqa: BLE001
            cookies = []
        return str(token or ""), cookies

    def _http_headers_for(
        self, token: str, cookies: list[dict[str, Any]]
    ) -> tuple[dict[str, str], dict[str, str]]:
        headers = {"User-Agent": settings.ARGUS_SCANNER_USER_AGENT}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        jar = {
            c["name"]: c["value"] for c in cookies if c.get("name") and c.get("value")
        }
        return headers, jar

    async def _probe_payload_injection(
        self,
        url: str,
        family: str,
        method: str,
        query_param: str,
        body: dict[str, Any] | None,
        inject_field: str,
    ) -> ToolOutcome:
        """家族化無害注入探測（nosql/ssti/xxe/command/lfi），一次跑整組 payload。

        設計：
        - 先打一次 baseline（原 URL／原 body），markers 必須「payload 回應出現
          且 baseline 不出現」才算命中——消掉回應本來就含 49／root: 類雜訊
        - 帶登入態（與 replay_request 同憑證來源），貼近真實攻擊條件
        - 工具只回觀察（每 payload 的狀態/長度/命中標記）；成立與否由 agent
          判定後 report_security_issue——維持觀察/判定分離契約
        安全：同源閘＋deep_mode runtime 再驗（同 replay_request 三層）。
        """
        if self.scan_job is None:
            return ToolOutcome(ok=False, result={"error": "no_scan_context"})
        from urllib.parse import (
            parse_qsl,
            urlencode,
            urlparse,
            urlsplit,
            urlunsplit,
        )

        from apps.scans.models import ScanJob

        if not (
            self.scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
            and self.scan_job.active_testing_authorized
        ):
            return ToolOutcome(ok=False, result={"error": "not_authorized_mode"})

        if family not in _PAYLOAD_FAMILIES:
            return ToolOutcome(ok=False, result={"error": "unknown_family"})
        method = method or "GET"
        if method not in ("GET", "POST"):
            return ToolOutcome(ok=False, result={"error": "method_not_allowed"})

        parsed = urlparse(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ToolOutcome(ok=False, result={"error": "invalid_url"})
        target_origin = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            target_origin = f"{target_origin}:{parsed.port}"
        if target_origin != self.scan_job.origin:
            return ToolOutcome(
                ok=False,
                result={"error": "cross_origin_forbidden", "allowed_origin": self.scan_job.origin},
            )

        parts = urlsplit(url)
        query_pairs = parse_qsl(parts.query, keep_blank_values=True)
        if method == "GET":
            if not query_param or not any(k == query_param for k, _ in query_pairs):
                return ToolOutcome(ok=False, result={"error": "no_such_query_param"})

            def _target_url(payload: str) -> str:
                new_qs = [
                    (k, payload) if k == query_param else (k, v) for k, v in query_pairs
                ]
                return urlunsplit(parts._replace(query=urlencode(new_qs)))
        else:
            if not isinstance(body, dict) or not inject_field:
                return ToolOutcome(ok=False, result={"error": "missing_inject_field"})

        token, cookies = await self._session_credentials()
        headers, jar = self._http_headers_for(token, cookies)

        import httpx

        def _send(target: str, m: str, b: dict[str, Any] | None) -> dict[str, Any]:
            with httpx.Client(
                headers=headers, cookies=jar, timeout=10.0, follow_redirects=False
            ) as client:
                if m == "POST":
                    r = client.post(target, json=b or {})
                else:
                    r = client.get(target)
            return {"status": r.status_code, "text": r.text or ""}

        def _run_family() -> dict[str, Any]:
            if method == "GET":
                base = _send(url, "GET", None)
            else:
                base = _send(url, "POST", body)
            base_text = base["text"]
            results = []
            for p in _PAYLOAD_FAMILIES[family]:
                if method == "GET":
                    target, send_body = _target_url(str(p["payload"])), None
                    m = "GET"
                else:
                    send_body = dict(body)
                    send_body[inject_field] = p["payload"]
                    target, m = url, "POST"
                try:
                    resp = _send(target, m, send_body)
                except Exception as exc:  # noqa: BLE001 — 單 payload 失敗不中斷整組
                    results.append(
                        {"kind": p["kind"], "error": exc.__class__.__name__}
                    )
                    continue
                markers_hit = [
                    mk
                    for mk in p["markers"]
                    if mk in resp["text"] and mk not in base_text
                ]
                results.append(
                    {
                        "kind": p["kind"],
                        "status": resp["status"],
                        "body_length": len(resp["text"]),
                        "markers_hit": markers_hit,
                    }
                )
            return {
                "family": family,
                "baseline": {"status": base["status"], "body_length": len(base_text)},
                "results": results,
            }

        try:
            observation = await asyncio.to_thread(_run_family)
        except Exception as exc:  # noqa: BLE001
            return ToolOutcome(
                ok=False, result={"error": f"probe_failed:{exc.__class__.__name__}"}
            )
        return ToolOutcome(ok=True, result=observation)

    async def _send_message(self, text: str, selector: str) -> ToolOutcome:
        """填入＋送出＋回撈（UI 互動一步化）。

        消除「type_text 填了沒按送出→真實 API 進不了 network log」的
        實證波動（#46/47：agent 猜端點 14 次全錯）。流程：偵測輸入框→
        fill→Enter→比對 network log 增量；無新請求則嘗試送出鈕；最後
        回傳新請求清單＋頁面新回應文字尾段。UI 操作層（同 click/
        type_text 邊界，context route 把關），不額外發任何 HTTP。
        """
        if not text.strip():
            return ToolOutcome(ok=False, result={"error": "empty_text"})

        _DETECT_SCRIPT = (
            "() => {"
            " const cands = ['textarea', 'input[type=text]', 'input[type=search]',"
            " '[contenteditable=true]'];"
            " for (const s of cands) {"
            "   for (const el of document.querySelectorAll(s)) {"
            "     const r = el.getBoundingClientRect();"
            "     if (r.width > 0 && r.height > 0 && !el.disabled) {"
            "       el.setAttribute('data-argus-target', '1');"
            "       return s;"
            "     }"
            "   }"
            " }"
            " return '';"
            "}"
        )

        try:
            if selector:
                loc = self.page.locator(selector).first
                await loc.fill(text, timeout=self.action_timeout_ms)
            else:
                detected = await self.page.evaluate(_DETECT_SCRIPT)
                if not detected:
                    return ToolOutcome(ok=False, result={"error": "no_input_found"})
                loc = self.page.locator(
                    f"{detected}[data-argus-target='1']"
                ).first
                await loc.fill(text, timeout=self.action_timeout_ms)

            before = len(self._network_log)
            await loc.press("Enter")
            await asyncio.sleep(1.5)

            # Enter 沒觸發新請求 → 嘗試送出鈕（常見按鈕式對話 UI）
            if len(self._network_log) == before:
                for btn_sel in (
                    "button[type=submit]",
                    "button[aria-label*='end' i]",
                    "button:has-text('Send')",
                    "button:has-text('送出')",
                ):
                    try:
                        btn = self.page.locator(btn_sel).first
                        await btn.click(timeout=1500)
                        await asyncio.sleep(1.5)
                        break
                    except Exception:  # noqa: BLE001 — 逐 selector 嘗試
                        continue

            new_requests = [
                {
                    "method": r.get("method"),
                    "url": r.get("url"),
                    "status": r.get("status"),
                }
                for r in self._network_log[before:]
            ]
            visible = await self.page.evaluate(
                "() => document.body && document.body.innerText"
                " ? document.body.innerText.slice(-1200) : ''"
            )
        except PlaywrightTimeoutError:
            return ToolOutcome(ok=False, result={"error": "timeout"})

        return ToolOutcome(
            ok=True,
            result={
                "sent": True,
                "new_requests": new_requests[:10],
                "page_tail": _truncate(str(visible), 1200),
            },
        )

    async def _collect_target_intel(
        self, target: str, urls: list[str]
    ) -> ToolOutcome:
        """帳號接管情報彙整：對多個同源端點帶憑證 GET，全文搜目標＋上下文抽取。

        把 WSTG-ATHN-09「答案來源推理」的資料蒐集從 LLM 多步推理降為單次
        檢索（#48 實證：agent 已讀備份檔但未連到答案——線索在 context 裡
        被淹沒）。GET only、同源閘＋deep_mode 再驗、每 URL 獨立容錯。
        """
        if self.scan_job is None:
            return ToolOutcome(ok=False, result={"error": "no_scan_context"})
        from urllib.parse import urlparse

        from apps.scans.models import ScanJob

        if not (
            self.scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
            and self.scan_job.active_testing_authorized
        ):
            return ToolOutcome(ok=False, result={"error": "not_authorized_mode"})
        if not target.strip() or not urls:
            return ToolOutcome(ok=False, result={"error": "missing_target_or_urls"})

        # 同源檢查（全部 URL）
        for u in urls:
            parsed = urlparse(u or "")
            origin = f"{parsed.scheme}://{parsed.hostname}"
            if parsed.port:
                origin = f"{origin}:{parsed.port}"
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return ToolOutcome(ok=False, result={"error": "invalid_url"})
            if origin != self.scan_job.origin:
                return ToolOutcome(
                    ok=False, result={"error": "cross_origin_forbidden"}
                )

        token, cookies = await self._session_credentials()
        headers, jar = self._http_headers_for(token, cookies)
        # 搜尋鍵：完整 target＋email 前綴（user@x → user）＋local 常見變體
        keys = {target.strip().lower()}
        if "@" in target:
            keys.add(target.split("@", 1)[0].lower())

        import httpx

        def _collect() -> dict[str, Any]:
            snippets: list[dict[str, Any]] = []
            errors: list[str] = []
            with httpx.Client(
                headers=headers, cookies=jar, timeout=10.0, follow_redirects=False
            ) as client:
                for u in urls:
                    try:
                        r = client.get(u)
                    except Exception as exc:  # noqa: BLE001 — 單 URL 失敗不中斷
                        errors.append(f"{exc.__class__.__name__}")
                        continue
                    text = r.text or ""
                    low = text.lower()
                    hits: list[tuple[int, str]] = []
                    for k in sorted(keys, key=len, reverse=True):
                        start = 0
                        while len(hits) < 6:
                            idx = low.find(k, start)
                            if idx < 0:
                                break
                            hits.append((idx, k))
                            start = idx + len(k)
                        if hits:
                            break
                    for idx, k in hits[:4]:
                        ctx = text[max(0, idx - 250) : idx + len(k) + 250]
                        snippets.append(
                            {
                                "url": u,
                                "matched": k,
                                "context": re.sub(r"\s+", " ", ctx).strip()[:500],
                            }
                        )
                        if len(snippets) >= 15:
                            break
                    if len(snippets) >= 15:
                        break
            return {"snippets": snippets, "errors": errors, "urls_scanned": len(urls)}

        try:
            observation = await asyncio.to_thread(_collect)
        except Exception as exc:  # noqa: BLE001
            return ToolOutcome(
                ok=False, result={"error": f"collect_failed:{exc.__class__.__name__}"}
            )
        return ToolOutcome(ok=True, result=observation)

    async def _take_screenshot(self) -> ToolOutcome:
        self._screenshot_counter += 1
        from pathlib import Path

        path = Path(self.screenshot_dir) / f"agent_step_{self._screenshot_counter}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(path), full_page=False)
        return ToolOutcome(ok=True, result={"path": str(path)})

    def _report_ux_issue(self, args: dict[str, Any]) -> ToolOutcome:
        from apps.agent.findings import cap_ux_severity

        severity = args.get("severity", "low")
        title = (args.get("title") or "").strip()[:255]
        description = (args.get("description") or "").strip()
        remediation = (args.get("remediation") or "").strip()
        selector = (args.get("selector") or "").strip()[:512]

        # 防呆：若描述夾帶程式碼修復片段，仍保留但 strip 過長
        description = description[:5000]
        remediation = remediation[:5000]

        if not title or not description:
            return ToolOutcome(ok=False, result={"error": "missing_title_or_description"})

        payload = {
            "severity": cap_ux_severity(severity),
            "title": title,
            "description": description,
            "remediation": remediation or "請檢視該流程的可用性並對齊使用者預期。",
            "selector": selector,
            "url": self.page.url,
        }
        return ToolOutcome(ok=True, result={"reported": True, "title": title}, issue=payload)

    async def _probe_unauthorized_access(self, url: str) -> ToolOutcome:
        """以無憑證的乾淨請求重放同源端點，驗證是否允許未授權存取。

        安全約束：
        - 強制**同源**（比對 scan_job.origin），與 _probe_sql_injection 同邊界。
        - 工具本身只在 deep_mode（active＋authorized）暴露 schema（build_tool_schemas）；
          runtime 再檢查一次 scan_mode/authorized，防 schema 外洩路徑。
        - 僅發一次普通 GET（scanner UA、無 cookie／token），不帶任何攻擊 payload；
          回應片段經 redact_url_query_values 後才回給 LLM 與持久化。

        回傳原始觀察（status／content_type／長度／片段）；**不由工具判定漏洞**——
        是否屬於應受保護資料由 agent 判斷後以 report_security_issue 回報，
        證據由 agent 附上，維持「證據鏈由觀察組成」的契約。
        """
        if self.scan_job is None:
            return ToolOutcome(ok=False, result={"error": "no_scan_context"})
        from urllib.parse import urlparse

        from django.conf import settings as dj_settings

        from apps.scans.models import ScanJob

        if not (
            self.scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
            and self.scan_job.active_testing_authorized
        ):
            return ToolOutcome(ok=False, result={"error": "not_authorized_mode"})

        parsed = urlparse(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ToolOutcome(ok=False, result={"error": "invalid_url"})
        target_origin = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            target_origin = f"{target_origin}:{parsed.port}"
        if target_origin != self.scan_job.origin:
            return ToolOutcome(
                ok=False,
                result={"error": "cross_origin_forbidden", "allowed_origin": self.scan_job.origin},
            )

        import httpx

        def _fetch() -> dict[str, Any]:
            # 不帶 cookie／Authorization：匿名重放。redirect 不跟隨，避免 open-redirect
            # 把探針導向他站；timeout 短，失敗即回結構化錯誤。
            with httpx.Client(
                headers={"User-Agent": dj_settings.ARGUS_SCANNER_USER_AGENT},
                timeout=10.0,
                follow_redirects=False,
            ) as client:
                r = client.get(url)
            snippet = (r.text or "")[:400]
            return {
                "status": r.status_code,
                "content_type": r.headers.get("content-type", ""),
                "body_length": len(r.content or b""),
                "body_snippet": snippet,
            }

        try:
            observation = await asyncio.to_thread(_fetch)
        except Exception as exc:  # noqa: BLE001 — 網路失敗回結構化錯誤不炸迴圈
            return ToolOutcome(
                ok=False, result={"error": f"request_failed:{exc.__class__.__name__}"}
            )
        observation["body_snippet"] = redact_url_query_values(
            str(observation.get("body_snippet", ""))
        )
        return ToolOutcome(ok=True, result=observation)

    async def _replay_request(
        self,
        url: str,
        method: str,
        body: dict[str, Any] | None,
        store_token_key: str = "",
        files: list[dict[str, Any]] | None = None,
    ) -> ToolOutcome:
        """以目前頁面的登入態重放同源請求（帶 session cookie 與 localStorage token）。

        agent 在 deep_mode（active＋authorized）已授權滲透範圍內，用此工具對
        已觀察過的 API 端點做「修改後重放」：改 id 測 IDOR、改數值測 business
        logic。工具只負責帶憑證發送與回傳觀察（遮罩後）；漏洞判定由 agent
        以 report_security_issue 附證據回報。

        安全約束：同源閘（比對 scan_job.origin）＋ deep_mode runtime 再驗；
        method 限 GET／POST（不允許 PUT/DELETE 等破壞性操作）；不跟隨 redirect。
        files 提供＝multipart/form-data（表單欄位=body；檔案內容限純文字
        探測內容，每請求上限 2 檔）——上傳面測試（WSTG-BUSL-08）用。
        """
        if self.scan_job is None:
            return ToolOutcome(ok=False, result={"error": "no_scan_context"})
        from urllib.parse import urlparse

        from apps.scans.models import ScanJob

        if not (
            self.scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
            and self.scan_job.active_testing_authorized
        ):
            return ToolOutcome(ok=False, result={"error": "not_authorized_mode"})

        method = (method or "GET").upper()
        if method not in ("GET", "POST", "PUT", "PATCH"):
            return ToolOutcome(ok=False, result={"error": "method_not_allowed"})

        # multipart：method 強制 POST；檔案內容限純文字探測（非執行檔本體）
        upload_files: list[tuple[str, tuple[str, str, str]]] = []
        if files:
            method = "POST"
            for f in files[:2]:
                if not isinstance(f, dict):
                    continue
                field = str(f.get("field") or "file")
                filename = str(f.get("filename") or "probe.txt")[:120]
                content = str(f.get("content") or "")[:8000]
                ctype = str(f.get("content_type") or "text/plain")[:60]
                upload_files.append((field, (filename, content, ctype)))

        parsed = urlparse(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ToolOutcome(ok=False, result={"error": "invalid_url"})
        target_origin = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            target_origin = f"{target_origin}:{parsed.port}"
        if target_origin != self.scan_job.origin:
            return ToolOutcome(
                ok=False,
                result={"error": "cross_origin_forbidden", "allowed_origin": self.scan_job.origin},
            )

        # 取得目前 session 的憑證（與 probe_payload_injection 共用）
        token, cookies = await self._session_credentials()

        import httpx

        def _fetch() -> dict[str, Any]:
            headers, jar = self._http_headers_for(token, cookies)
            with httpx.Client(
                headers=headers, cookies=jar, timeout=10.0, follow_redirects=False
            ) as client:
                if upload_files:
                    r = client.post(url, data=body or {}, files=upload_files)
                elif method == "POST":
                    r = client.post(url, json=body or {})
                elif method == "PUT":
                    r = client.put(url, json=body or {})
                elif method == "PATCH":
                    r = client.patch(url, json=body or {})
                else:
                    r = client.get(url)
            return {
                "status": r.status_code,
                "content_type": r.headers.get("content-type", ""),
                "body_length": len(r.content or b""),
                "body_snippet": (r.text or "")[:400],
                # token 抽取必須用完整回應：JWT 常超過 snippet 的 400 字元，
                # 截斷字串會讓 json.loads 失敗、token 永遠存不進去
                "_full_body": r.text or "",
            }

        try:
            observation = await asyncio.to_thread(_fetch)
        except Exception as exc:  # noqa: BLE001 — 網路失敗回結構化錯誤不炸迴圈
            return ToolOutcome(
                ok=False, result={"error": f"request_failed:{exc.__class__.__name__}"}
            )
        # 登入端點支援：回應 JSON 裡的 token 寫入 localStorage，讓 agent 的
        # 後續重放自動帶登入態（SPA 慣例）。token 不回傳給 LLM、不持久化。
        token_stored = False
        full_body = observation.pop("_full_body", "")
        if store_token_key:
            try:
                data = json.loads(full_body or "{}")
            except (json.JSONDecodeError, TypeError):
                data = {}
            token_value = (
                ((data.get("authentication") or {}).get("token"))
                or data.get("token")
                or data.get("access_token")
                or data.get("accessToken")
                or ""
            )
            if token_value:
                try:
                    await self.page.evaluate(
                        "([k, v]) => localStorage.setItem(k, v)",
                        [store_token_key, str(token_value)],
                    )
                    token_stored = True
                except Exception:
                    pass
        observation["body_snippet"] = redact_url_query_values(
            str(observation.get("body_snippet", ""))
        )
        # JWT 一串幾百字元只會灌爆 context 又遮住後面的有用欄位（如登入回應
        # 的 bid）；壓縮成長度標記，token 本體 agent 不需要
        observation["body_snippet"] = re.sub(
            r"eyJ[A-Za-z0-9._-]{80,}",
            lambda m: f"[JWT len={len(m.group(0))}]",
            str(observation["body_snippet"]),
        )
        observation["authenticated"] = bool(token or cookies)
        if store_token_key:
            observation["token_stored"] = token_stored
        return ToolOutcome(ok=True, result=observation)

    def _forge_jwt(
        self, payload: dict[str, Any], alg: str, secret: str
    ) -> ToolOutcome:
        """本地偽造 JWT（jwt_tool 方法論）：alg=none 無簽／HS256 弱密鑰清單。

        純本地計算不發請求；token 交回 agent 以 replay_request 驗證接受度。
        deep_only＋runtime 再驗（run() 分派處）。
        """
        import base64
        import hashlib
        import hmac

        def _b64e(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).decode().rstrip("=")

        clean_payload = {
            k: v for k, v in (payload or {}).items() if isinstance(k, str)
        }
        tokens: list[dict[str, Any]] = []

        def _build(header: dict[str, Any], sig: str) -> None:
            segments = [
                _b64e(json.dumps(header, separators=(",", ":")).encode()),
                _b64e(json.dumps(clean_payload, separators=(",", ":")).encode()),
                sig,
            ]
            tokens.append(
                {
                    "secret_used": header.get("alg", ""),
                    "token": ".".join(segments),
                }
            )

        if alg == "none":
            _build({"alg": "none", "typ": "JWT"}, "")
        elif alg == "HS256":
            secrets = [secret] if secret else _WEAK_JWT_SECRETS
            for cand in secrets:
                header = {"alg": "HS256", "typ": "JWT"}
                signing_input = (
                    _b64e(json.dumps(header, separators=(",", ":")).encode())
                    + "."
                    + _b64e(json.dumps(clean_payload, separators=(",", ":")).encode())
                )
                sig = hmac.new(
                    cand.encode(), signing_input.encode(), hashlib.sha256
                ).digest()
                _build(header, _b64e(sig))
        else:
            return ToolOutcome(ok=False, result={"error": "unsupported_alg"})

        return ToolOutcome(ok=True, result={"tokens": tokens[:11]})

    def _report_security_issue(self, args: dict[str, Any]) -> ToolOutcome:
        """把 agent 觀察到的資安問題組成 security finding（走 probe_sql_injection
        同一條 security_finding 落地鏈，由 loop → persist_agent_security_findings 寫入）。

        觀察型回報的 severity 上限 medium：AI 的觀察只證明「看到了什麼」，不證明能被利用。
        **high／critical 只有在 agent 真的用主動工具確認過（self._active_confirmations 非空：
        replay_request／probe_payload_injection／probe_unauthorized_access／probe_sql_injection／
        run_nuclei 任一成功）且本次回報帶 verified=true 時才保留**（2026-10-10 放寬：不需 Kali
        sqlmap，用 agent 自己的工具驗證即可，但「有驗證」這道關卡保留，擋純臆測自評高風險）。
        2026-09-28 報告審查時 agent 把 WAF 攔截頁回顯的來源 IP 判成高風險，即為缺驗證之例。
        """
        from urllib.parse import urlparse

        from apps.scans.scanners import make_finding
        from apps.scans.security.ip_context import describe_ips

        severity = str(args.get("severity", "low")).lower()
        # verified 需 agent 自己宣告，且必須真的呼叫過主動工具才算數（防純自評）
        tool_verified = bool(args.get("verified")) and bool(self._active_confirmations)
        if severity in {"critical", "high"} and not tool_verified:
            severity = "medium"
        if severity not in {"critical", "high", "medium", "low", "info"}:
            severity = "low"
        title = (args.get("title") or "").strip()[:255]
        description = (args.get("description") or "").strip()[:5000]
        evidence = (args.get("evidence") or "").strip()[:5000]
        remediation = (args.get("remediation") or "").strip()[:5000]
        url = (args.get("url") or "").strip()
        if not title or not description or not evidence:
            return ToolOutcome(
                ok=False, result={"error": "missing_required_fields"}
            )

        safe_url = redact_url_query_values(url) if url else ""
        full_description = description + (f"（觀察端點：{safe_url}）" if safe_url else "")
        hostname = urlparse(url or getattr(self.scan_job, "normalized_url", "") or "").hostname
        ip_notes = describe_ips(evidence, hostname or "")
        ip_text = ("\n證據中的 IP 自動核對：" + "；".join(ip_notes) + "。") if ip_notes else ""
        finding = make_finding(
            category="security",
            severity=severity,
            rule_id="agent-observed-security",
            title=title,
            description=(
                f"AI Agent 在實際操作網站時觀察到：{full_description}{ip_text}\n"
                + (
                    "AI Agent 以主動工具重現並確認此問題可被利用，附有擷取的回應作為證據。"
                    if tool_verified
                    else "這是 AI 的觀察與判讀，附有擷取的回應作為證據，"
                    "但未經工具或人工驗證可被利用。"
                )
            ),
            remediation=remediation or "依證據內容對應的存取控制／資料保護強化。",
            evidence=evidence,
            evidence_source="hermes_agent",
            evidence_json={
                "type": "text",
                "source": "hermes_agent",
                "tool_verified": tool_verified,
                "excerpt": evidence[:1000],
                "assessment": {
                    "condition": "攻擊者能利用這項觀察，取得原本拿不到的資訊、權限或繞過既有防護。",
                    "observed": "AI Agent 送出的請求與擷取到的回應內容（見檢測依據）。"
                    + (f"IP 核對：{'；'.join(ip_notes)}。" if ip_notes else ""),
                    "missing": (
                        "AI 已用主動工具重現，仍建議資安人員就實際影響做最終確認。"
                        if tool_verified
                        else "AI 對影響的判讀未經工具重現或人工確認；觀察到資訊不等於能被利用。"
                    ),
                    "verify": (
                        "依檢測依據重送相同請求確認回應一致，再由資安人員評估該資訊能否被實際利用。"
                    ),
                },
            },
            impact_area="vulnerability",
        )
        return ToolOutcome(ok=True, result={"reported": title}, security_finding=finding)

    async def _probe_sql_injection(self, url: str) -> ToolOutcome:
        """LLM 自主觸發的授權範圍內 SQLi 主動驗證。

        安全約束：
        - 強制**同源**（比對 scan_job.origin）：即使 LLM 給出他站 URL 也拒絕，維持
          agent 既有的 same-origin 邊界（見 agent/CLAUDE.md）。
        - 必須帶 query 參數（sqlmap 需要注入點）。
        - 授權鎖完全交給 kali_tools.run_sqlmap 的三重鎖（ARGUS_KALI_ENABLED + active +
          authorized）；未授權時回 blocked，LLM 會知道無法執行。
        - subprocess 阻塞，包進 to_thread 避免卡住 event loop。

        Task 6：直接信任 res["confirmed"]，不再解析 stdout（Task 3 讓 stdout 恆為 ""）。
        result 不含 target URL；Finding 的 description 使用遮罩後的 URL。
        """
        if self.scan_job is None:
            return ToolOutcome(ok=False, result={"error": "no_scan_context"})
        from urllib.parse import urlparse

        parsed = urlparse(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ToolOutcome(ok=False, result={"error": "invalid_url"})
        target_origin = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            target_origin = f"{target_origin}:{parsed.port}"
        if target_origin != self.scan_job.origin:
            return ToolOutcome(
                ok=False,
                result={"error": "cross_origin_forbidden", "allowed_origin": self.scan_job.origin},
            )
        if "?" not in url or "=" not in url:
            return ToolOutcome(ok=False, result={"error": "no_query_parameter"})

        from apps.scans.security.kali_tools import run_sqlmap

        res = await asyncio.to_thread(run_sqlmap, url, self.scan_job.id)
        if res.get("blocked_reason"):
            return ToolOutcome(
                ok=False,
                result={"confirmed": False, "blocked": res["blocked_reason"]},
            )
        if not res.get("confirmed"):
            return ToolOutcome(
                ok=True,
                result={"confirmed": False, "error": res.get("error", "")},
            )

        # 確認可注入 → 產 security finding（欄位與 validate_findings_with_kali 一致）
        from apps.scans.scanners import make_finding

        safe_url = redact_url_query_values(url)
        evidence_summary = res.get("evidence_summary") or {}
        finding = make_finding(
            category="security",
            severity="critical",
            rule_id="kali-sqlmap-sqli",
            title="SQL Injection 已由 Hermes-Agent 觸發 sqlmap 主動驗證可利用",
            description=(
                f"Hermes-Agent 在授權的主動測試中自主判斷並對 {safe_url} 觸發 sqlmap，"
                "確認存在可被利用的 SQL injection 注入點。此為已驗證漏洞，非僅靜態判斷。"
            ),
            remediation=(
                "使用參數化查詢（prepared statements）或 ORM，對所有使用者輸入做嚴格驗證與轉義，"
                "並以最小權限資料庫帳號連線。"
            ),
            evidence=json.dumps(evidence_summary, sort_keys=True),
            impact_area="vulnerability",
            confidence=1.0,
        )
        return ToolOutcome(
            ok=True,
            result={
                "confirmed": True,
                "correlation_id": "kali-sqlmap-sqli",
            },
            security_finding=finding,
        )
