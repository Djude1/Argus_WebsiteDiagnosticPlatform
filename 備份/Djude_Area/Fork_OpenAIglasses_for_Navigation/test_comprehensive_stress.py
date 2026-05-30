#!/usr/bin/env python3
"""
綜合壓力測試 — 語音關鍵字觸發系統
覆蓋現有測試未涵蓋的盲區：
  1. 完整對話生命週期（standby → wake → command → end → standby）
  2. _normalize_cn 邊界測試（空字串、超長、純標點、全空白）
  3. INTERRUPT_KEYWORDS 深度變體測試
  4. 主動模式下的指令匹配（喚醒後下指令）
  5. 狀態衝突（待機說結束詞、主動說喚醒詞）
  6. 混合語言 / Unicode（英文+中文、emoji、全形字）
  7. 重複/快速輸入（連續喚醒、快速切換）
  8. 旁路模式（APP bypass_wake 路徑）
  9. Google STT 真實輸出模式模擬
  10. _s2t 轉換深度驗證
"""
import os, sys, unicodedata

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from asr_core import (
    WAKE_WORDS, END_WORDS, INTERRUPT_KEYWORDS,
    _normalize_cn, _s2t, GoogleASR,
)

_MAMBO_VARIANTS = GoogleASR._MAMBO_VARIANTS


# ═══════════════════════════════════════════════════════════════════════════════
# 模擬 GoogleASR 的完整狀態機
# ═══════════════════════════════════════════════════════════════════════════════

class FakeASR:
    """模擬 GoogleASR 的狀態機，追蹤 standby/active 模式切換"""

    def __init__(self, bypass_wake: bool = False):
        self.mode = "standby"
        self.bypass_wake = bypass_wake
        self.events = []       # 記錄所有觸發事件
        self.commands = []     # 記錄派發給 AI 的指令

    def _check_wake(self, text: str) -> bool:
        """模擬 GoogleASR._check_wake_word"""
        if self.bypass_wake:
            self.events.append(("bypass", text))
            self.commands.append(text)
            self.mode = "active"
            return True

        norm = _normalize_cn(text)
        matched = any(v in norm for v in _MAMBO_VARIANTS)
        if matched:
            self.events.append(("wake", text))
            self.mode = "active"
            return True
        else:
            self.events.append(("ignored", text))
            return False

    def _check_end(self, text: str) -> bool:
        """模擬 GoogleASR._handle_active 中的結束詞檢查"""
        norm = _normalize_cn(text)
        for w in END_WORDS:
            if w and _normalize_cn(w) in norm:
                self.events.append(("end", text))
                self.mode = "standby"
                return True
        return False

    def _check_interrupt(self, text: str) -> bool:
        """檢查中斷熱詞"""
        norm = _normalize_cn(text)
        return any(w and _normalize_cn(w) in norm for w in INTERRUPT_KEYWORDS)

    def feed(self, text: str, is_final: bool = True):
        """模擬餵入一段 STT 結果"""
        if self.mode == "standby":
            if is_final:
                self._check_wake(text)
        else:
            # active mode
            if is_final:
                if not self._check_end(text):
                    if not self._check_interrupt(text):
                        self.events.append(("command", text))
                        self.commands.append(text)
                    else:
                        self.events.append(("interrupt", text))

    def reset(self):
        self.mode = "standby"
        self.events.clear()
        self.commands.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 1：完整對話生命週期
# ═══════════════════════════════════════════════════════════════════════════════

def test_lifecycle():
    print("=" * 70)
    print("測試 1：完整對話生命週期 — standby → wake → command → end → standby")
    print("=" * 70)

    test_cases = [
        # (輸入序列, 預期事件序列, 描述)
        (
            ["哈囉曼波", "開始導航", "謝謝曼波"],
            [("wake", "哈囉曼波"), ("command", "開始導航"), ("end", "謝謝曼波")],
            "標準生命週期：喚醒→指令→結束"
        ),
        (
            ["曼波", "幫我找一下紅牛", "謝謝曼波"],
            [("wake", "曼波"), ("command", "幫我找一下紅牛"), ("end", "謝謝曼波")],
            "只用曼波喚醒"
        ),
        (
            ["漫波", "停止導航", "謝謝漫波"],
            [("wake", "漫波"), ("command", "停止導航"), ("end", "謝謝漫波")],
            "漫波變體喚醒+結束"
        ),
        (
            ["你好", "曼波", "開始過馬路", "謝謝曼波"],
            [("ignored", "你好"), ("wake", "曼波"), ("command", "開始過馬路"), ("end", "謝謝曼波")],
            "先打招呼被忽略→再說曼波喚醒"
        ),
        (
            ["曼波", "曼波", "謝謝曼波"],
            [("wake", "曼波"), ("command", "曼波"), ("end", "謝謝曼波")],
            "連續兩次曼波：第一次喚醒、第二次當指令"
        ),
        (
            ["曼波", "謝謝漫波"],
            [("wake", "曼波"), ("end", "謝謝漫波")],
            "喚醒後直接結束（無指令）"
        ),
        (
            ["曼波", "幫我看看這是什麼", "我想去便利商店", "謝謝曼波"],
            [("wake", "曼波"), ("command", "幫我看看這是什麼"), ("command", "我想去便利商店"), ("end", "謝謝曼波")],
            "多輪對話：2個指令後結束"
        ),
        (
            ["你好", "今天天氣不錯", "開始導航"],
            [("ignored", "你好"), ("ignored", "今天天氣不錯"), ("ignored", "開始導航")],
            "不說曼波，所有語音被忽略"
        ),
        (
            ["曼波", "停下所有功能"],
            [("wake", "曼波"), ("interrupt", "停下所有功能")],
            "喚醒後立刻中斷"
        ),
    ]

    passed = 0
    failed = 0

    for inputs, expected_events, desc in test_cases:
        asr = FakeASR()
        for text in inputs:
            asr.feed(text)

        # 比對事件序列
        actual_events = [(e[0], e[1]) for e in asr.events]
        ok = actual_events == expected_events

        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  ❌ {desc}")
            print(f"     輸入: {inputs}")
            print(f"     預期: {expected_events}")
            print(f"     實際: {actual_events}")

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 生命週期測試: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有生命週期測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗")

    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 2：_normalize_cn 邊界測試
# ═══════════════════════════════════════════════════════════════════════════════

def test_normalize_edge_cases():
    print("=" * 70)
    print("測試 2：_normalize_cn 邊界測試 — 空字串、超長、純標點、全空白")
    print("=" * 70)

    test_cases = [
        # (輸入, 預期不crash, 預期結果特徵, 描述)
        ("", True, "", "空字串"),
        ("   ", True, "", "全空白"),
        ("\t\n\r", True, "", "tab/換行/歸位"),
        ("\u3000", True, "", "全形空白"),
        ("，。！？、；：「」『』（）", True, True, "純中文標點"),
        ("曼波", True, "曼波", "正常中文"),
        ("a" * 10000, True, "a" * 10000, "超長字串（10000字元）"),
        ("曼" + "\u0000" + "波", True, True, "含null字元"),
        ("\u200b曼波\u200b", True, True, "含零寬空格"),
        ("\ufeff曼波", True, True, "含BOM"),
    ]

    passed = 0
    failed = 0

    for text, should_not_crash, expected_feature, desc in test_cases:
        try:
            result = _normalize_cn(text)
            crashed = False
        except Exception as e:
            crashed = True
            result = None

        if crashed:
            if should_not_crash:
                failed += 1
                print(f"  ❌ {desc} — crash！（不應crash）")
            else:
                passed += 1
        else:
            # 檢查預期特徵
            if isinstance(expected_feature, str):
                ok = result == expected_feature
            elif isinstance(expected_feature, bool):
                ok = True  # 只要沒crash就算通過
            else:
                ok = True

            if ok:
                passed += 1
            else:
                failed += 1
                print(f"  ❌ {desc}")
                print(f"     輸入: {repr(text[:50])}")
                print(f"     預期特徵: {repr(expected_feature)}")
                print(f"     實際結果: {repr(result[:50])}")

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 邊界測試: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有邊界測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗")

    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 3：INTERRUPT_KEYWORDS 深度變體測試
# ═══════════════════════════════════════════════════════════════════════════════

def test_interrupt_deep():
    print("=" * 70)
    print("測試 3：INTERRUPT 深度測試 — 停下/停止所有功能的變體")
    print("=" * 70)

    # 目前 INTERRUPT_KEYWORDS = {"停下所有功能", "停止所有功能"}
    test_cases = [
        # ── 標準 ──
        ("停下所有功能", True, "標準-繁體"),
        ("停止所有功能", True, "標準-繁體"),

        # ── 簡體 ──
        ("停下所有功能", True, "簡體→繁(s2t)"),
        ("停止所有功能", True, "簡體→繁(s2t)"),

        # ── ASR 誤辨變體 ──
        ("停瞎所有功能", False, "誤辨-下→瞎"),
        ("停值所有功能", False, "誤辨-止→值"),
        ("停制所有功能", False, "誤辨-止→制"),
        ("停下手有功能", False, "誤辨-所→手"),
        ("聽下所有功能", False, "誤辨-停→聽"),
        ("庭下所有功能", False, "誤辨-停→庭"),

        # ── 口語化 ──
        ("停下全部功能", False, "口語-所有→全部（不在INTERRUPT中）"),
        ("停止全部功能", False, "口語-所有→全部"),
        ("停", False, "極短-只有停"),
        ("停下", False, "極短-只有停下"),

        # ── 語氣詞 ──
        ("嗯停下所有功能", True, "前綴語氣詞"),
        ("停下所有功能啊", True, "後綴語氣詞"),
        ("就是停下所有功能", True, "口頭禪前綴"),

        # ── 含標點 ──
        ("停下所有功能！", True, "含驚嘆號"),
        ("停下所有功能。", True, "含句號"),

        # ── 長句中包含 ──
        ("我想停下所有功能", True, "長句-前綴"),
        ("停下所有功能好不好", True, "長句-後綴"),
    ]

    passed = 0
    failed = 0

    for text, should_match, desc in test_cases:
        norm = _normalize_cn(text)
        matched = any(w and _normalize_cn(w) in norm for w in INTERRUPT_KEYWORDS)

        ok = (matched == should_match)
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  ❌ 「{text}」({desc})")
            print(f"     預期: {'匹配' if should_match else '不匹配'}, 實際: {'匹配' if matched else '不匹配'}")

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 INTERRUPT 深度測試: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有 INTERRUPT 測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗（多為 ASR 同音字誤辨，可接受）")

    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 4：狀態衝突 — 邊界狀態下的行為
# ═══════════════════════════════════════════════════════════════════════════════

def test_state_conflicts():
    print("=" * 70)
    print("測試 4：狀態衝突 — 邊界狀態下的行為")
    print("=" * 70)

    test_cases = [
        # (輸入序列, 預期最終模式, 預期事件數, 描述)
        (
            ["謝謝曼波"],
            "active", 1,
            "待機說「謝謝曼波」→ 含曼波→觸發喚醒（非結束）"
        ),
        (
            ["曼波", "謝謝曼波"],
            "standby", 2,
            "喚醒後說「謝謝曼波」→ 正常結束"
        ),
        (
            ["曼波", "曼波", "謝謝曼波"],
            "standby", 3,
            "喚醒後再說「曼波」→ 當指令→再說「謝謝曼波」→ 結束"
        ),
        (
            ["曼波", "停下所有功能"],
            "active", 2,
            "喚醒後中斷 → 模式仍為active（中斷不切回standby）"
        ),
        (
            ["曼波", "謝謝曼波", "開始導航"],
            "standby", 3,
            "喚醒→結束→開始導航（結束後standby，「開始導航」無曼波→被忽略）"
        ),
        (
            ["曼波", "謝謝曼波", "曼波"],
            "active", 3,
            "喚醒→結束→再喚醒（完整循環）"
            # 結束後standby，"曼波"→再次喚醒
        ),
    ]

    passed = 0
    failed = 0

    for inputs, expected_final_mode, expected_event_count, desc in test_cases:
        asr = FakeASR()
        for text in inputs:
            asr.feed(text)

        ok = (asr.mode == expected_final_mode and len(asr.events) == expected_event_count)

        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  ❌ {desc}")
            print(f"     輸入: {inputs}")
            print(f"     預期模式: {expected_final_mode}, 實際: {asr.mode}")
            print(f"     預期事件數: {expected_event_count}, 實際: {len(asr.events)}")
            print(f"     事件: {asr.events}")

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 狀態衝突測試: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有狀態衝突測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗")

    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 5：混合語言 / Unicode 極端場景
# ═══════════════════════════════════════════════════════════════════════════════

def test_mixed_language():
    print("=" * 70)
    print("測試 5：繁體中文使用者真實場景 — 只會說繁體中文的使用者")
    print("=" * 70)

    test_cases = [
        # (輸入, 預期是否觸發喚醒, 描述)
        # ── 純繁體中文 ──
        ("曼波", True, "純繁體-曼波"),
        ("漫波", True, "純繁體-漫波變體"),
        ("哈囉曼波", True, "純繁體-哈囉曼波"),
        ("你好", False, "純繁體-你好（無曼波）"),
        ("哈囉世界", False, "純繁體-哈囉世界（無曼波）"),

        # ── ASR 可能的標點/空白 ──
        ("曼波！", True, "含驚嘆號"),
        ("曼波。", True, "含句號"),
        ("曼波？", True, "含問號"),
        (" 曼波 ", True, "前後空白"),

        # ── 含數字（導航場景可能出現）──
        ("曼波1號", True, "曼波+數字"),
        ("曼波第2代", True, "曼波+序號"),

        # ── 不應觸發（使用者日常對話）──
        ("今天天氣好好喔", False, "日常對話-天氣"),
        ("我想去便利商店", False, "日常對話-商店"),
        ("等一下紅綠燈", False, "日常對話-紅綠燈"),
        ("你好你好", False, "日常對話-打招呼"),

        # ── emoji 場景（ASR 不會輸出，但防禦性測試）──
        ("曼波🤖", True, "曼波+emoji"),
    ]

    passed = 0
    failed = 0

    for text, should_wake, desc in test_cases:
        norm = _normalize_cn(text)
        matched = any(v in norm for v in _MAMBO_VARIANTS)

        ok = (matched == should_wake)
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  ❌ 「{text}」({desc})")
            print(f"     norm: '{norm}'")
            print(f"     預期: {'觸發' if should_wake else '不觸發'}, 實際: {'觸發' if matched else '不觸發'}")

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 混合語言測試: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有混合語言測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗")

    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 6：重複/快速輸入 — 壓力測試
# ═══════════════════════════════════════════════════════════════════════════════

def test_rapid_repeated_input():
    print("=" * 70)
    print("測試 6：重複/快速輸入 — 連續喚醒、快速切換、壓力測試")
    print("=" * 70)

    test_cases = [
        # (輸入序列, 預期事件序列類型, 描述)
        (
            ["曼波"] * 10,
            ["wake"] + ["command"] * 9,
            "連續10次曼波：第1次喚醒，後9次當指令"
        ),
        (
            ["曼波", "謝謝曼波"] * 5,
            ["wake", "end"] * 5,
            "連續5次喚醒→結束循環"
        ),
        (
            ["你好"] * 100,
            ["ignored"] * 100,
            "100次無關語音全部忽略"
        ),
        (
            ["曼波"] + ["開始導航"] * 50 + ["謝謝曼波"],
            ["wake"] + ["command"] * 50 + ["end"],
            "1次喚醒→50個指令→1次結束"
        ),
        (
            ["漫波", "慢播", "滿波", "們波"],
            ["wake", "command", "command", "command"],
            "不同曼波變體：第1次喚醒，其餘當指令"
        ),
    ]

    passed = 0
    failed = 0

    for inputs, expected_types, desc in test_cases:
        asr = FakeASR()
        for text in inputs:
            asr.feed(text)

        actual_types = [e[0] for e in asr.events]
        ok = actual_types == expected_types

        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  ❌ {desc}")
            print(f"     預期事件數: {len(expected_types)}, 實際: {len(actual_types)}")
            if len(actual_types) <= 20:
                print(f"     預期: {expected_types}")
                print(f"     實際: {actual_types}")
            else:
                print(f"     前10個預期: {expected_types[:10]}...")
                print(f"     前10個實際: {actual_types[:10]}...")

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 重複/快速輸入測試: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有重複/快速輸入測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗")

    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 7：旁路模式（APP bypass_wake）
# ═══════════════════════════════════════════════════════════════════════════════

def test_bypass_mode():
    print("=" * 70)
    print("測試 7：旁路模式（APP bypass_wake）— 不需要喚醒詞")
    print("=" * 70)

    test_cases = [
        # (輸入序列, 全部應被接受為指令, 描述)
        (
            ["開始導航"],
            True,
            "APP模式：直接說指令（無需曼波）"
        ),
        (
            ["你好", "開始導航", "停止導航"],
            True,
            "APP模式：多個指令直接派發"
        ),
        (
            ["哈囉", "今天天氣好", "幫我看看這是什麼"],
            True,
            "APP模式：含打招呼和對話"
        ),
    ]

    passed = 0
    failed = 0

    for inputs, all_accepted, desc in test_cases:
        asr = FakeASR(bypass_wake=True)
        for text in inputs:
            asr.feed(text)

        # 旁路模式下，所有語音都應被接受為指令
        actual_types = [e[0] for e in asr.events]
        # 第一個應該是 bypass，之後都是 command
        expected = True
        if not actual_types:
            expected = False
        elif actual_types[0] != "bypass":
            expected = False
        # 旁路模式第一次進入後，後續都是 active mode 的 command
        for t in actual_types[1:]:
            if t not in ("command", "end", "interrupt"):
                expected = False

        ok = (expected == all_accepted)
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  ❌ {desc}")
            print(f"     事件: {asr.events}")

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 旁路模式測試: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有旁路模式測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗")

    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 8：Google STT 真實輸出模式
# ═══════════════════════════════════════════════════════════════════════════════

def test_real_asr_patterns():
    print("=" * 70)
    print("測試 8：Google STT 真實輸出模式 — 模擬實際 ASR 回傳格式")
    print("=" * 70)

    test_cases = [
        # (STT 輸出, 預期喚醒, 描述)
        # Google STT 可能的標點格式
        ("哈囉，曼波", True, "Google STT 自動加逗號"),
        ("哈囉曼波。", True, "Google STT 自動加句號"),
        ("哈囉曼波，請幫我導航。", True, "Google STT 自動標點+後綴指令"),
        ("哈囉  曼波", True, "Google STT 雙空格"),
        (" 哈囉曼波 ", True, "前後空白"),

        # Google STT 的 cmn-Hant-TW 可能輸出
        ("哈囉曼波", True, "繁體標準"),
        ("哈喽曼波", True, "簡體嘍（經s2t轉換）"),
        ("哈囉漫波", True, "ASR 漫波變體"),
        ("謝謝 曼波", True, "含空格的結束詞（也會觸發喚醒）"),

        # Google STT 可能把環境音也辨識出來
        ("[噪音]曼波", True, "Google STT 可能的噪音標記（罕見）"),
        ("(音樂)哈囉曼波", True, "含括號標記"),

        # Google STT streaming 的 partial → final
        # partial 可能先出現「哈囉」→ 最終變成「哈囉曼波」
        # 但 _handle_result 在 standby 只處理 final，所以 partial 不會觸發

        # Google STT 的自動斷句
        ("哈囉曼波\n", True, "含換行"),
        ("哈囉\r\n曼波", True, "Windows換行"),

        # 常見的 Google STT timestamp 相關的額外文字
        ("哈囉曼波.", True, "英文句號結尾"),
    ]

    passed = 0
    failed = 0

    for text, should_wake, desc in test_cases:
        norm = _normalize_cn(text)
        matched = any(v in norm for v in _MAMBO_VARIANTS)

        ok = (matched == should_wake)
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  ❌ 「{repr(text)}」({desc})")
            print(f"     norm: '{norm}'")
            print(f"     預期: {'觸發' if should_wake else '不觸發'}, 實際: {'觸發' if matched else '不觸發'}")

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 STT 真實輸出測試: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有 STT 真實輸出測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗")

    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 9：_s2t 轉換深度驗證
# ═══════════════════════════════════════════════════════════════════════════════

def test_s2t_deep():
    print("=" * 70)
    print("測試 9：_s2t 轉換深度驗證 — 所有常用簡體→繁體對應")
    print("=" * 70)

    # 測試常用簡→繁對應（特別是 ASR 可能輸出的）
    test_cases = [
        ("导航", "導航", True),
        ("开始", "開始", True),
        ("停止", "停止", True),
        ("谢谢", "謝謝", True),
        ("过马路", "過馬路", True),
        ("红绿灯", "紅綠燈", True),
        ("说明书", "說明書", True),
        ("帮我看", "幫我看", True),
        ("帮我找", "幫我找", True),
        ("识别", "識別", True),
        ("录像", "錄像", True),
        ("导航结束", "導航結束", True),
        # 喚醒詞相關
        ("哈喽曼波", "哈囉曼波", True),
        ("谢谢漫播", "謝謝漫播", True),
        # 不應轉換的
        ("Hello", "Hello", True),
        ("123", "123", True),
        ("", "", True),
        # 邊界：半簡半繁
        ("导航結束", "導航結束", True),
        ("开始過馬路", "開始過馬路", True),
    ]

    passed = 0
    failed = 0

    for simp, expected_trad, should_match in test_cases:
        trad = _s2t(simp)
        ok = (trad == expected_trad) == should_match

        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  ❌ 「{simp}」→「{trad}」(預期「{expected_trad}」)")

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 s2t 深度測試: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有 s2t 深度測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗")

    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 10：END_WORDS 在主動模式下的完整性
# ═══════════════════════════════════════════════════════════════════════════════

def test_end_words_in_active():
    print("=" * 70)
    print("測試 10：END_WORDS 主動模式完整性 — 所有結束詞變體")
    print("=" * 70)

    test_cases = [
        ("謝謝曼波", True, "標準"),
        ("謝謝 曼波", True, "含空格"),
        ("謝謝，曼波", True, "含逗號"),
        ("謝謝漫波", True, "漫波變體"),
        ("謝謝漫播", True, "漫播變體"),
        ("謝謝慢播", True, "慢播變體"),
        ("謝謝慢波", True, "慢波變體"),
        ("謝謝滿波", True, "滿波變體"),
        ("嗯謝謝曼波", True, "前綴語氣詞"),
        ("謝謝曼波啊", True, "後綴語氣詞"),
        ("謝謝", False, "只有謝謝"),
        ("曼波", False, "只有曼波"),
        ("多謝曼波", False, "多謝≠謝謝"),
        ("感謝曼波", False, "感謝≠謝謝"),
    ]

    passed = 0
    failed = 0

    for text, should_end, desc in test_cases:
        norm = _normalize_cn(text)
        matched = any(w and _normalize_cn(w) in norm for w in END_WORDS)

        ok = (matched == should_end)
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  ❌ 「{text}」({desc})")
            print(f"     預期: {'結束' if should_end else '不結束'}, 實際: {'結束' if matched else '不結束'}")

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 END_WORDS 主動模式測試: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有 END_WORDS 測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗")

    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  綜合壓力測試 — 語音關鍵字觸發系統                        ║")
    print("║  覆蓋生命週期、邊界、狀態衝突、混合語言、壓力場景        ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    total_passed = 0
    total_failed = 0

    results = []

    suites = [
        ("測試 1: 生命週期", test_lifecycle),
        ("測試 2: 邊界測試", test_normalize_edge_cases),
        ("測試 3: INTERRUPT深度", test_interrupt_deep),
        ("測試 4: 狀態衝突", test_state_conflicts),
        ("測試 5: 混合語言", test_mixed_language),
        ("測試 6: 重複/壓力", test_rapid_repeated_input),
        ("測試 7: 旁路模式", test_bypass_mode),
        ("測試 8: STT真實輸出", test_real_asr_patterns),
        ("測試 9: s2t深度", test_s2t_deep),
        ("測試 10: END完整性", test_end_words_in_active),
    ]

    for name, func in suites:
        p, f = func()
        total_passed += p
        total_failed += f
        results.append((name, p, f))
        print()

    # ═══ 最終總結 ═══
    print("=" * 70)
    print("📊 綜合壓力測試總結")
    print("=" * 70)

    for name, p, f in results:
        status = "✅" if f == 0 else "⚠️"
        print(f"  {status} {name}: {p}/{p+f} = {p/(p+f)*100:.1f}%")

    total = total_passed + total_failed
    print(f"\n  📊 總計: {total_passed}/{total} = {total_passed/total*100:.1f}%")

    if total_failed == 0:
        print("\n✅ 綜合壓力測試全部通過！")
    else:
        print(f"\n⚠️ {total_failed} 條測試失敗")

    print()
    print("═" * 70)
    print("📋 盲區分析")
    print("═" * 70)
    for name, p, f in results:
        if f > 0:
            print(f"  ⚠️ {name}: {f} 條失敗（多為 ASR 同音字誤辨或極端邊界，可接受）")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
