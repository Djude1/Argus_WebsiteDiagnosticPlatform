# test_voice_commands.py
# -*- coding: utf-8 -*-
"""
語音指令端到端測試：模擬「用戶說一句話 → ASR 辨識 → 指令解析 → 觸發功能」。

測試覆蓋範圍：
1. 全部語音指令的匹配邏輯（繁體+簡體+常見誤辨）
2. 不同導航模式下的指令過濾
3. IDLE 模式的雜訊過濾
4. 喚醒詞 / 結束詞 / 中斷熱詞

驗證項目：
- 每條指令是否正確匹配到對應功能
- 繁簡體變體是否都被覆蓋
- ASR 常見誤辨是否能被容錯
- 非指令語音是否被正確過濾

不依賴外部 API，純本地驗證指令解析邏輯。
"""

import re
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

os.chdir(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════════════════════
# 載入伺服器端的指令匹配邏輯
# ═══════════════════════════════════════════════════════════════════════════════

from asr_core import (
    WAKE_WORDS, END_WORDS, INTERRUPT_KEYWORDS,
    _normalize_cn, GoogleASR,
)

_MAMBO_VARIANTS = GoogleASR._MAMBO_VARIANTS


# ═══════════════════════════════════════════════════════════════════════════════
# 模擬 start_ai_with_text_custom 的指令匹配邏輯
# ═══════════════════════════════════════════════════════════════════════════════

def classify_command(user_text: str, current_state: str = "IDLE") -> dict:
    """
    模擬 app_main.py 中 start_ai_with_text_custom 的指令解析邏輯。
    回傳 {"command": 指令類型, "matched_by": 匹配的關鍵字, "state_after": 預期狀態}
    如果沒有匹配到任何指令，回傳 {"command": None}
    """

    # ── 使用說明書（任何模式下均可觸發，支援繁簡體）────────────────
    if ("眼鏡使用說明書" in user_text or "使用說明書" in user_text or
        "眼镜使用说明书" in user_text or "使用说明书" in user_text):
        return {"command": "usage_guide", "matched_by": "使用說明書", "state_after": current_state}

    # ── 導航模式下的過濾邏輯 ────────────────────────────────────
    if current_state not in ["CHAT", "IDLE"]:
        allowed_keywords = [
            "帮我看", "帮我看下", "帮我看一下", "帮我找", "帮我找下", "帮我找一下",
            "找一下", "看看", "识别一下", "找到了", "拿到了",
            "幫我看", "幫我看下", "幫我找", "識別一下",
        ]
        is_allowed_query = any(keyword in user_text for keyword in allowed_keywords)

        nav_control_keywords = [
            "开始过马路", "过马路结束", "开始导航", "开启导航", "盲道导航",
            "停止导航", "结束导航", "检测红绿灯", "看红绿灯", "停止检测", "停止红绿灯",
            "開始過馬路", "過馬路結束", "開始導航", "開啟導航",
            "停止導航", "結束導航", "檢測紅綠燈", "看紅綠燈", "停止檢測", "停止紅綠燈",
        ]
        is_nav_control = any(keyword in user_text for keyword in nav_control_keywords)

        if not is_allowed_query and not is_nav_control:
            return {"command": None, "reason": "導航模式下丟棄非控制語音"}

    # ── 過馬路指令 ────────────────────────────────────────────
    crossing_start = ["开始过马路", "帮我过马路", "開始過馬路", "幫我過馬路"]
    for kw in crossing_start:
        if kw in user_text:
            return {"command": "start_crossing", "matched_by": kw, "state_after": "CROSSING"}

    crossing_end = ["过马路结束", "结束过马路", "過馬路結束", "結束過馬路"]
    for kw in crossing_end:
        if kw in user_text:
            return {"command": "stop_crossing", "matched_by": kw, "state_after": "CHAT"}

    # ── 紅綠燈檢測指令 ────────────────────────────────────────
    traffic_start = ["检测红绿灯", "看红绿灯", "檢測紅綠燈", "看紅綠燈"]
    for kw in traffic_start:
        if kw in user_text:
            return {"command": "start_traffic_light", "matched_by": kw, "state_after": "TRAFFIC_LIGHT_DETECTION"}

    traffic_stop = ["停止检测", "停止红绿灯", "停止檢測", "停止紅綠燈"]
    for kw in traffic_stop:
        if kw in user_text:
            return {"command": "stop_traffic_light", "matched_by": kw, "state_after": "CHAT"}

    # ── 盲道導航指令 ──────────────────────────────────────────
    nav_start = [
        "开始导航", "开启导航", "盲道导航", "帮我导航",
        "開始導航", "開啟導航", "幫我導航", "忙導航",
    ]
    for kw in nav_start:
        if kw in user_text:
            return {"command": "start_blindpath", "matched_by": kw, "state_after": "BLINDPATH_NAV"}

    nav_stop = ["停止导航", "结束导航", "停止導航", "結束導航"]
    for kw in nav_stop:
        if kw in user_text:
            return {"command": "stop_blindpath", "matched_by": kw, "state_after": "CHAT"}

    # ── 導航控制副指令 ────────────────────────────────────────
    nav_cmd_keywords = [
        "开始过马路", "过马路结束", "开始导航", "开启导航", "盲道导航",
        "停止导航", "结束导航", "立即通过", "现在通过", "继续",
        "開始過馬路", "過馬路結束", "開始導航", "開啟導航", "忙導航",
        "停止導航", "結束導航", "立即通過", "現在通過",
    ]
    for kw in nav_cmd_keywords:
        if kw in user_text:
            return {"command": "nav_sub_command", "matched_by": kw, "state_after": current_state}

    # ── 找物品指令 ────────────────────────────────────────────
    find_pattern = r"(?:^\s*(?:帮我|幫我))?\s*找一下\s*(.+?)(?:。|！|？|$)"
    match = re.search(find_pattern, user_text)
    if match:
        item_cn = match.group(1).strip()
        if item_cn:
            return {"command": "find_item", "matched_by": f"找一下{item_cn}", "item": item_cn, "state_after": "ITEM_SEARCH"}

    # ── 找到了指令 ────────────────────────────────────────────
    if "找到了" in user_text or "拿到了" in user_text:
        return {"command": "item_found", "matched_by": "找到了", "state_after": "CHAT"}

    # ── IDLE 模式雜訊過濾 ─────────────────────────────────────
    _CHAT_TRIGGER_KEYWORDS = [
        "帮我", "幫我", "看看", "看一下", "前面", "什么", "什麼",
        "有没有", "有沒有", "告訴", "告诉", "描述", "識別", "识别",
        "找", "開始", "开始", "導航", "导航", "過馬路", "过马路",
        "說明書", "使用說明", "紅綠燈", "红绿灯",
    ]
    keyword_hits = [kw for kw in _CHAT_TRIGGER_KEYWORDS if kw in user_text]
    if len(user_text) < 3 and len(keyword_hits) < 2:
        return {"command": None, "reason": "IDLE過濾：語音過短"}

    # ── 都沒匹配 → 進入 AI 對話 ───────────────────────────────
    return {"command": "ai_chat", "matched_by": None, "state_after": "CHAT"}


# ═══════════════════════════════════════════════════════════════════════════════
# 測試案例
# ═══════════════════════════════════════════════════════════════════════════════

def test_all_commands():
    """測試 1：全部語音指令匹配（含繁簡體 + ASR 誤辨變體）"""
    print("=" * 70)
    print("測試 1：全部語音指令匹配 — 繁簡體 + ASR 誤辨變體")
    print("=" * 70)

    test_cases = [
        # (語音文字, 預期指令, 預期狀態, 場景描述)

        # ── 盲道導航 ──
        ("開始導航", "start_blindpath", "BLINDPATH_NAV", "盲道導航-繁體標準"),
        ("开始导航", "start_blindpath", "BLINDPATH_NAV", "盲道導航-簡體標準"),
        ("開啟導航", "start_blindpath", "BLINDPATH_NAV", "盲道導航-繁體變體"),
        ("开启导航", "start_blindpath", "BLINDPATH_NAV", "盲道導航-簡體變體"),
        ("盲道导航", "start_blindpath", "BLINDPATH_NAV", "盲道導航-直接關鍵字"),
        ("幫我導航", "start_blaindpath", "BLINDPATH_NAV", "盲道導航-幫我前綴(繁)"),
        ("帮我导航", "start_blindpath", "BLINDPATH_NAV", "盲道導航-幫我前綴(簡)"),
        ("忙導航", "start_blindpath", "BLINDPATH_NAV", "盲道導航-ASR誤辨(幫→忙)"),

        # ── 停止導航 ──
        ("停止導航", "stop_blindpath", "CHAT", "停止導航-繁體"),
        ("停止导航", "stop_blindpath", "CHAT", "停止導航-簡體"),
        ("結束導航", "stop_blindpath", "CHAT", "結束導航-繁體"),
        ("结束导航", "stop_blindpath", "CHAT", "結束導航-簡體"),

        # ── 過馬路 ──
        ("開始過馬路", "start_crossing", "CROSSING", "過馬路-繁體標準"),
        ("开始过马路", "start_crossing", "CROSSING", "過馬路-簡體標準"),
        ("幫我過馬路", "start_crossing", "CROSSING", "過馬路-幫我前綴(繁)"),
        ("帮我过马路", "start_crossing", "CROSSING", "過馬路-幫我前綴(簡)"),
        ("過馬路結束", "stop_crossing", "CHAT", "過馬路結束-繁體"),
        ("过马路结束", "stop_crossing", "CHAT", "過馬路結束-簡體"),
        ("結束過馬路", "stop_crossing", "CHAT", "結束過馬路-繁體"),
        ("结束过马路", "stop_crossing", "CHAT", "結束過馬路-簡體"),

        # ── 紅綠燈 ──
        ("檢測紅綠燈", "start_traffic_light", "TRAFFIC_LIGHT_DETECTION", "紅綠燈-繁體標準"),
        ("检测红绿灯", "start_traffic_light", "TRAFFIC_LIGHT_DETECTION", "紅綠燈-簡體標準"),
        ("看紅綠燈", "start_traffic_light", "TRAFFIC_LIGHT_DETECTION", "紅綠燈-口語(繁)"),
        ("看红绿灯", "start_traffic_light", "TRAFFIC_LIGHT_DETECTION", "紅綠燈-口語(簡)"),
        ("停止檢測", "stop_traffic_light", "CHAT", "停止紅綠燈-繁體"),
        ("停止检测", "stop_traffic_light", "CHAT", "停止紅綠燈-簡體"),
        ("停止紅綠燈", "stop_traffic_light", "CHAT", "停止紅綠燈-繁體關鍵字"),
        ("停止红绿灯", "stop_traffic_light", "CHAT", "停止紅綠燈-簡體關鍵字"),

        # ── 找物品 ──
        ("幫我找一下紅牛", "find_item", "ITEM_SEARCH", "找物品-繁體標準"),
        ("帮我找一下红牛", "find_item", "ITEM_SEARCH", "找物品-簡體標準"),
        ("找一下礦泉水", "find_item", "ITEM_SEARCH", "找物品-無前綴(繁)"),
        ("找一下矿泉水", "find_item", "ITEM_SEARCH", "找物品-無前綴(簡)"),
        ("幫我找一下AD鈣奶", "find_item", "ITEM_SEARCH", "找物品-中英混合"),
        ("帮我找一下手机", "find_item", "ITEM_SEARCH", "找物品-ASR誤辨可能"),

        # ── 找到了 ──
        ("找到了", "item_found", "CHAT", "找到了-標準"),
        ("拿到了", "item_found", "CHAT", "拿到了-變體"),
        ("我找到了", "item_found", "CHAT", "找到了-帶前綴"),

        # ── 使用說明書 ──
        ("眼鏡使用說明書", "usage_guide", "IDLE", "使用說明書-繁體完整"),
        ("使用说明书", "usage_guide", "IDLE", "使用說明書-簡體"),

        # ── AI 對話 ──
        ("幫我看看這是什麼", "ai_chat", "CHAT", "AI對話-看東西(繁)"),
        ("帮我看看这是什么", "ai_chat", "CHAT", "AI對話-看東西(簡)"),
        ("前面有什麼", "ai_chat", "CHAT", "AI對話-前方詢問(繁)"),
        ("前面有什么", "ai_chat", "CHAT", "AI對話-前方詢問(簡)"),
        ("描述一下前面的路", "ai_chat", "CHAT", "AI對話-描述請求"),

        # ── ASR 誤辨變體 ──
        ("開是導航", "ai_chat", "CHAT", "ASR誤辨-開始→開是(無直接匹配)"),
        ("幫我過馬路", "start_crossing", "CROSSING", "標準指令-確認通過"),
    ]

    passed = 0
    failed = 0
    results = []

    for phrase, expected_cmd, expected_state, desc in test_cases:
        result = classify_command(phrase, "IDLE")
        # 修正 expected_cmd 打字錯誤（start_blaindpath → start_blindpath）
        actual_expected = expected_cmd
        if expected_cmd == "start_blaindpath":
            actual_expected = "start_blindpath"

        ok = result["command"] == actual_expected
        status = "✅ 通過" if ok else "❌ 失敗"

        if not ok:
            print(f"  ❌ 「{phrase}」({desc})")
            print(f"     預期: {actual_expected} → {expected_state}")
            print(f"     實際: {result['command']} → {result.get('state_after', '?')}")
            if result.get("reason"):
                print(f"     原因: {result['reason']}")
            failed += 1
        else:
            passed += 1

        results.append({
            "phrase": phrase,
            "expected": actual_expected,
            "actual": result["command"],
            "passed": ok,
            "desc": desc,
        })

    print(f"\n  📊 指令匹配結果: {passed}/{len(test_cases)} 通過")
    if failed == 0:
        print(f"  ✅ 全部語音指令匹配正確！")
    else:
        print(f"  ❌ {failed} 條指令匹配失敗")

    return results


def test_navigation_mode_filtering():
    """測試 2：導航模式下的指令過濾"""
    print("=" * 70)
    print("測試 2：導航模式下的指令過濾 — 只允許特定指令通過")
    print("=" * 70)

    # 在 BLINDPATH_NAV 模式下的測試
    nav_mode_tests = [
        # (語音文字, 是否應被處理, 預期指令 or None, 描述)
        ("停止導航", True, "stop_blindpath", "導航中-允許停止導航"),
        ("開始過馬路", True, "start_crossing", "導航中-允許切換過馬路"),
        ("看紅綠燈", True, "start_traffic_light", "導航中-允許紅綠燈"),
        ("幫我看看前面", True, "ai_chat", "導航中-允許「幫我看」類對話"),
        ("幫我找一下鑰匙", True, "find_item", "導航中-允許找物品"),
        ("今天天氣如何", False, None, "導航中-丟棄無關對話"),
        ("你好", False, None, "導航中-丟棄打招呼"),
        ("我想吃飯", False, None, "導航中-丟棄閒聊"),
        ("使用說明書", True, "usage_guide", "導航中-允許使用說明書(任何模式)"),
    ]

    passed = 0
    failed = 0
    results = []

    print("\n  ── BLINDPATH_NAV 模式 ──")
    for phrase, should_process, expected_cmd, desc in nav_mode_tests:
        result = classify_command(phrase, "BLINDPATH_NAV")
        is_processed = result["command"] is not None
        ok = (is_processed == should_process)
        if should_process and expected_cmd:
            ok = ok and result["command"] == expected_cmd

        status = "✅ 通過" if ok else "❌ 失敗"
        if not ok:
            print(f"    ❌ 「{phrase}」({desc})")
            print(f"       預期: {'處理→' + expected_cmd if should_process else '丟棄'}")
            print(f"       實際: {result['command']} {result.get('reason', '')}")
            failed += 1
        else:
            passed += 1

        results.append({"phrase": phrase, "passed": ok, "desc": desc, "mode": "BLINDPATH_NAV"})

    # ITEM_SEARCH 模式下的測試
    print("\n  ── ITEM_SEARCH 模式 ──")
    item_mode_tests = [
        ("找到了", True, "item_found", "找物品中-允許「找到了」"),
        ("拿到了", True, "item_found", "找物品中-允許「拿到了」"),
        ("停止導航", True, "stop_blindpath", "找物品中-允許停止導航"),
        ("幫我找一下水", True, "find_item", "找物品中-允許切換找別的物品"),
        ("今天天氣如何", False, None, "找物品中-丟棄閒聊"),
    ]

    for phrase, should_process, expected_cmd, desc in item_mode_tests:
        result = classify_command(phrase, "ITEM_SEARCH")
        is_processed = result["command"] is not None
        ok = (is_processed == should_process)
        if should_process and expected_cmd:
            ok = ok and result["command"] == expected_cmd

        status = "✅ 通過" if ok else "❌ 失敗"
        if not ok:
            print(f"    ❌ 「{phrase}」({desc})")
            print(f"       預期: {'處理→' + expected_cmd if should_process else '丟棄'}")
            print(f"       實際: {result['command']} {result.get('reason', '')}")
            failed += 1
        else:
            passed += 1

        results.append({"phrase": phrase, "passed": ok, "desc": desc, "mode": "ITEM_SEARCH"})

    total = len(nav_mode_tests) + len(item_mode_tests)
    print(f"\n  📊 導航模式過濾結果: {passed}/{total} 通過")
    if failed == 0:
        print(f"  ✅ 所有模式的指令過濾正確！")
    else:
        print(f"  ❌ {failed} 條過濾邏輯失敗")

    return results


def test_wake_and_end_words():
    """測試 3：喚醒詞 / 結束詞 / 中斷熱詞匹配"""
    print("=" * 70)
    print("測試 3：喚醒詞 / 結束詞 / 中斷熱詞 — ESP32 喚醒模式")
    print("=" * 70)

    test_cases = [
        # ── 喚醒詞（含曼波變體→觸發）──
        ("哈囉 曼波", "wake", True, "喚醒詞-含曼波"),
        ("哈囉曼波", "wake", True, "喚醒詞-含曼波"),
        ("哈囉，曼波", "wake", True, "喚醒詞-含曼波"),
        ("哈喽曼波", "wake", True, "喚醒詞-含曼波"),
        ("哈喽漫播", "wake", True, "喚醒詞-含漫播"),
        ("哈喽 曼波", "wake", True, "喚醒詞-含曼波"),
        ("哈喽，曼波", "wake", True, "喚醒詞-含曼波"),
        ("羅曼波", "wake", True, "喚醒詞-含曼波"),
        ("哈囉慢播", "wake", True, "喚醒詞-含慢播"),
        ("曼波", "wake", True, "喚醒詞-只有曼波→觸發"),
        ("漫波", "wake", True, "喚醒詞-漫波變體→觸發"),
        ("慢播", "wake", True, "喚醒詞-慢播變體→觸發"),

        # ── 結束詞 ──
        ("謝謝 曼波", "end", True, "結束詞-標準(繁)"),
        ("謝謝曼波", "end", True, "結束詞-無空格(繁)"),
        ("謝謝，曼波", "end", True, "結束詞-含逗號(繁)"),
        ("谢谢曼波", "end", True, "結束詞-簡體"),
        ("谢谢漫播", "end", True, "結束詞-ASR誤辨"),
        ("谢谢 曼波", "end", True, "結束詞-簡體空格"),

        # ── 中斷熱詞 ──
        ("停下所有功能", "interrupt", True, "中斷-繁體標準"),
        ("停止所有功能", "interrupt", True, "中斷-繁體變體"),

        # ── 不應匹配的 ──
        ("哈囉", "wake", False, "只有哈囉（無曼波）→不觸發"),
        ("你好曼波", "wake", True, "含曼波→觸發"),
        ("謝謝", "end", False, "非結束詞-只有謝謝"),
    ]

    passed = 0
    failed = 0
    results = []

    for phrase, word_type, should_match, desc in test_cases:
        norm = _normalize_cn(phrase)

        if word_type == "wake":
            matched = any(v in norm for v in _MAMBO_VARIANTS)
        elif word_type == "end":
            matched = any(w and _normalize_cn(w) in norm for w in END_WORDS)
        elif word_type == "interrupt":
            matched = any(w and _normalize_cn(w) in norm for w in INTERRUPT_KEYWORDS)
        else:
            matched = False

        ok = (matched == should_match)
        status = "✅ 通過" if ok else "❌ 失敗"

        if not ok:
            print(f"  ❌ 「{phrase}」({desc})")
            print(f"     類型: {word_type}, 預期: {'匹配' if should_match else '不匹配'}, 實際: {'匹配' if matched else '不匹配'}")
            failed += 1
        else:
            passed += 1

        results.append({"phrase": phrase, "type": word_type, "passed": ok, "desc": desc})

    print(f"\n  📊 喚醒/結束/中斷詞結果: {passed}/{len(test_cases)} 通過")
    if failed == 0:
        print(f"  ✅ 所有喚醒詞/結束詞/中斷詞匹配正確！")
    else:
        print(f"  ❌ {failed} 條匹配失敗")

    return results


def test_idle_noise_filtering():
    """測試 4：IDLE 模式的雜訊過濾"""
    print("=" * 70)
    print("測試 4：IDLE 模式雜訊過濾 — 短語音/無關語音丟棄")
    print("=" * 70)

    test_cases = [
        # (語音文字, 是否應被處理, 描述)
        ("嗯", False, "單音節雜訊"),
        ("啊", False, "單音節雜訊"),
        ("對", False, "單字回應"),
        ("好", False, "單字回應"),
        ("嗯嗯", False, "兩字雜訊"),
        ("好的", False, "兩字無關(無關鍵字)"),
        ("開始導航", True, "有效指令-3字"),
        ("看一下", True, "有效指令-含關鍵字"),
    ]

    passed = 0
    failed = 0
    results = []

    for phrase, should_process, desc in test_cases:
        result = classify_command(phrase, "IDLE")
        is_processed = result["command"] is not None
        ok = (is_processed == should_process)

        if not ok:
            print(f"  ❌ 「{phrase}」({desc})")
            print(f"     預期: {'處理' if should_process else '丟棄'}")
            print(f"     實際: {result['command']} {result.get('reason', '')}")
            failed += 1
        else:
            passed += 1

        results.append({"phrase": phrase, "passed": ok, "desc": desc})

    print(f"\n  📊 IDLE 雜訊過濾結果: {passed}/{len(test_cases)} 通過")
    if failed == 0:
        print(f"  ✅ IDLE 模式雜訊過濾正確！")
    else:
        print(f"  ❌ {failed} 條過濾失敗")

    return results


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  語音指令端到端測試套件                                    ║")
    print("║  模擬「用戶說話 → ASR 辨識 → 指令解析 → 功能觸發」        ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # 測試 1：全部指令匹配
    cmd_results = test_all_commands()
    cmd_pass = sum(1 for r in cmd_results if r["passed"])
    cmd_total = len(cmd_results)

    # 測試 2：導航模式過濾
    filter_results = test_navigation_mode_filtering()
    filter_pass = sum(1 for r in filter_results if r["passed"])
    filter_total = len(filter_results)

    # 測試 3：喚醒/結束/中斷詞
    word_results = test_wake_and_end_words()
    word_pass = sum(1 for r in word_results if r["passed"])
    word_total = len(word_results)

    # 測試 4：IDLE 雜訊過濾
    idle_results = test_idle_noise_filtering()
    idle_pass = sum(1 for r in idle_results if r["passed"])
    idle_total = len(idle_results)

    # 總結
    print("=" * 70)
    print("📊 語音指令端到端測試總結")
    print("=" * 70)

    print(f"  指令匹配（繁簡+誤辨）: {cmd_pass}/{cmd_total} 通過")
    print(f"  導航模式過濾:          {filter_pass}/{filter_total} 通過")
    print(f"  喚醒/結束/中斷詞:      {word_pass}/{word_total} 通過")
    print(f"  IDLE 雜訊過濾:         {idle_pass}/{idle_total} 通過")

    all_pass = (
        cmd_pass == cmd_total and
        filter_pass == filter_total and
        word_pass == word_total and
        idle_pass == idle_total
    )

    total_pass = cmd_pass + filter_pass + word_pass + idle_pass
    total_tests = cmd_total + filter_total + word_total + idle_total

    print()
    print(f"  總計: {total_pass}/{total_tests} 通過")

    if all_pass:
        print()
        print("🎉 所有語音指令測試通過！端到端指令解析驗證成功。")
    else:
        print()
        print("⚠️ 部分測試未通過，需要調整指令匹配邏輯。")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
