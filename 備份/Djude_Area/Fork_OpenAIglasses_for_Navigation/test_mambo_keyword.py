# test_mambo_keyword.py
# -*- coding: utf-8 -*-
"""
曼波（曼波/漫波/漫播/慢播）喚醒詞 / 結束詞 / 熱詞 反覆測試。

測試覆蓋：
1. 喚醒詞匹配：_MAMBO_VARIANTS 的所有變體
2. 結束詞匹配：END_WORDS 的所有變體
3. Google STT 熱詞（speech_contexts）：確認熱詞清單涵蓋所有可能的 ASR 誤辨
4. 各種使用者說話場景：
   - 正常發音「哈囉曼波」
   - 快語速「哈曼波」「哈曼」
   - 慢語速「哈～囉～曼波」
   - 台灣國語口音
   - ASR 常見誤辨（漫波、漫播、慢播、羅曼波等）
   - 含語氣詞「哈囉曼波啊」「那個哈囉曼波」
   - 雜訊中的短語
5. 不應誤觸發的場景（日常對話中提到「曼波」）

驗證項目：
- 每種變體是否能正確匹配到喚醒詞/結束詞
- 熱詞清單是否涵蓋所有常見 ASR 誤辨
- 不應誤觸發的場景是否被正確拒絕
"""

import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from asr_core import (
    WAKE_WORDS, END_WORDS, INTERRUPT_KEYWORDS,
    _normalize_cn, _s2t, GoogleASR,
)

_MAMBO_VARIANTS = GoogleASR._MAMBO_VARIANTS


# ═══════════════════════════════════════════════════════════════════════════════
# 模擬 Google STT 可能的輸出（含各種 ASR 誤辨場景）
# ═══════════════════════════════════════════════════════════════════════════════

# Google STT speech_contexts 中的熱詞（boost=20.0）
SPEECH_CONTEXT_PHRASES = [
    "哈囉曼波", "哈囉 曼波", "謝謝曼波", "謝謝 曼波",
    "羅曼波", "哈囉慢播", "哈囉嗎",
    "曼波", "漫波", "漫播", "慢播",
    # 新增：常見 ASR 誤辨變體
    "慢波", "滿波", "們波",
    "哈羅曼波", "哈洛曼波",
    "哈囉慢波", "哈囉漫波", "哈囉滿波",
]


def check_wake_match(text: str) -> bool:
    """模擬 GoogleASR._check_wake_word 中的喚醒詞匹配邏輯
    核心規則：只要偵測到「曼波」（含 ASR 誤辨變體）即觸發"""
    norm = _normalize_cn(text)
    matched = any(v in norm for v in _MAMBO_VARIANTS)
    return matched


def check_end_match(text: str) -> bool:
    """模擬 GoogleASR._handle_active 中的結束詞匹配邏輯"""
    norm = _normalize_cn(text)
    return any(w and _normalize_cn(w) in norm for w in END_WORDS)


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 1：喚醒詞變體反覆測試
# ═══════════════════════════════════════════════════════════════════════════════

def test_wake_word_variants():
    print("=" * 70)
    print("測試 1：曼波喚醒詞變體 — 反覆測試所有可能的使用者說法和 ASR 輸出")
    print("=" * 70)

    test_cases = [
        # ── 標準喚醒詞（含「曼波」變體）──
        ("哈囉 曼波", True, "標準-含曼波"),
        ("哈囉曼波", True, "標準-含曼波"),
        ("哈囉，曼波", True, "標準-含曼波"),
        ("哈喽曼波", True, "標準-含曼波"),
        ("哈喽漫播", True, "標準-含漫播"),
        ("哈喽 曼波", True, "標準-含曼波"),
        ("哈喽，曼波", True, "標準-含曼波"),
        ("羅曼波", True, "含曼波"),
        ("哈囉慢播", True, "含慢播"),
        ("哈囉嗎", False, "無曼波變體（僅哈囉）"),

        # ── 只有「曼波」變體也能觸發 ──
        ("曼波", True, "只有曼波"),
        ("漫波", True, "只有漫波"),
        ("慢播", True, "只有慢播"),
        ("慢波", True, "只有慢波"),
        ("滿波", True, "只有滿波"),
        ("們波", True, "只有們波"),
        ("哈囉", False, "只有哈囉（無曼波）"),
        ("哈喽", False, "只有哈嘍（無曼波）"),
        ("哈啰", False, "只有哈囉（無曼波）"),

        # ── 繁簡混合（經 _s2t 轉換後應能匹配）──
        ("哈喽曼波", True, "簡體→繁體(含曼波)"),
        ("哈囉漫波", True, "含漫波"),
        ("哈囉慢播", True, "含慢播"),
        ("哈囉漫播", True, "含漫播"),

        # ── 快語速變體 ──
        ("哈曼波", True, "快語速-含曼波"),
        ("哈曼", False, "極短-無曼波變體"),

        # ── 慢語速 / 語氣詞 ──
        ("哈囉曼波啊", True, "語氣詞-含曼波"),
        ("嗯哈囉曼波", True, "語氣詞-含曼波"),
        ("那個哈囉曼波", True, "口頭禪-含曼波"),
        ("就是哈囉曼波", True, "口頭禪-含曼波"),

        # ── ASR 其他可能的誤辨 ──
        ("哈羅曼波", True, "含曼波"),
        ("哈洛曼波", True, "含曼波"),
        ("哈漏曼波", True, "含曼波"),
        ("阿羅曼波", True, "含曼波"),
        ("沙羅曼波", True, "含曼波"),
        ("哈囉慢波", True, "含慢波"),
        ("哈囉滿波", True, "含滿波"),
        ("哈囉半波", False, "半波不在變體中"),
        ("哈囉賣波", False, "賣波不在變體中"),
        ("哈囉們波", True, "含們波"),

        # ── 含標點符號 ──
        ("哈囉曼波！", True, "含曼波"),
        ("哈囉曼波。", True, "含曼波"),
        ("哈囉曼波？", True, "含曼波"),
        ("「哈囉曼波」", True, "含曼波"),

        # ── 長句中包含喚醒詞 ──
        ("我想說哈囉曼波", True, "含曼波"),
        ("哈囉曼波請幫我導航", True, "含曼波"),
        ("你好哈囉曼波可以嗎", True, "含曼波"),

        # ── 不應觸發的（無曼波變體）──
        ("你好曼波", True, "含曼波→觸發"),
        ("哈囉世界", False, "無曼波變體"),
        ("羅曼", False, "只有羅曼（無波）"),
        ("謝謝曼波", True, "含曼波→觸發（也是結束詞）"),
    ]

    passed = 0
    failed = 0
    results = []

    for text, expected, desc in test_cases:
        matched = check_wake_match(text)
        ok = (matched == expected)
        status = "✅" if ok else "❌"

        if not ok:
            print(f"  ❌ 「{text}」({desc})")
            print(f"     預期: {'匹配' if expected else '不匹配'}, 實際: {'匹配' if matched else '不匹配'}")
            failed += 1
        else:
            passed += 1

        results.append({"text": text, "expected": expected, "actual": matched, "passed": ok, "desc": desc})

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 喚醒詞變體覆蓋率: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有喚醒詞變體測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗，需調整")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 2：結束詞變體反覆測試
# ═══════════════════════════════════════════════════════════════════════════════

def test_end_word_variants():
    print("=" * 70)
    print("測試 2：曼波結束詞變體 — 謝謝曼波的所有可能說法")
    print("=" * 70)

    test_cases = [
        # ── END_WORDS 中定義的 ──
        ("謝謝 曼波", True, "標準-空格"),
        ("謝謝曼波", True, "標準-無空格"),
        ("謝謝，曼波", True, "標準-含逗號"),
        ("谢谢曼波", True, "簡體-謝→谢"),
        ("谢谢漫播", True, "簡體+誤辨(漫播)"),
        ("谢谢 曼波", True, "簡體-空格"),

        # ── 繁簡混合（經 _s2t 後）──
        ("谢谢曼波", True, "簡→繁(谢→謝)"),
        ("謝謝漫波", True, "繁體-漫波"),
        ("謝謝慢播", True, "繁體-慢播"),
        ("謝謝漫播", True, "繁體-漫播"),

        # ── ASR 其他誤辨 ──
        ("謝謝慢波", True, "誤辨-播→波"),
        ("謝謝滿波", True, "誤辨-曼→滿"),
        ("謝謝們波", False, "極端誤辨-曼→們（可接受）"),
        ("謝協曼波", False, "極端誤辨-謝→謝協（可接受）"),
        ("謝寫曼波", False, "極端誤辨-謝→謝寫（可接受）"),

        # ── 語氣詞 ──
        ("謝謝曼波啊", True, "語氣詞-後綴"),
        ("嗯謝謝曼波", True, "語氣詞-前綴"),

        # ── 不應觸發 ──
        ("謝謝", False, "只有謝謝（無曼波）"),
        ("曼波", False, "只有曼波（無謝謝）"),
        ("謝謝你", False, "謝謝你（無曼波）"),
        ("謝謝幫忙", False, "謝謝幫忙（無曼波）"),
    ]

    passed = 0
    failed = 0
    results = []

    for text, expected, desc in test_cases:
        matched = check_end_match(text)
        ok = (matched == expected)
        status = "✅" if ok else "❌"

        if not ok:
            print(f"  ❌ 「{text}」({desc})")
            print(f"     預期: {'匹配' if expected else '不匹配'}, 實際: {'匹配' if matched else '不匹配'}")
            failed += 1
        else:
            passed += 1

        results.append({"text": text, "expected": expected, "actual": matched, "passed": ok, "desc": desc})

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 結束詞變體覆蓋率: {passed}/{len(test_cases)} = {rate:.1f}%")
    if failed == 0:
        print(f"  ✅ 所有結束詞變體測試通過！")
    else:
        print(f"  ⚠️ {failed} 條測試失敗，需調整")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 3：Google STT 熱詞覆蓋率分析
# ═══════════════════════════════════════════════════════════════════════════════

def test_speech_context_coverage():
    print("=" * 70)
    print("測試 3：Google STT 熱詞（speech_contexts）覆蓋率分析")
    print("=" * 70)

    # 所有可能的 ASR 誤辨結果（使用者說「哈囉曼波」或「謝謝曼波」）
    possible_asr_outputs = [
        # 曼波 的各種誤辨
        "曼波", "漫波", "漫播", "慢播", "慢波", "滿波", "們波",
        "半波", "賣波", "門波", "悶波",
        # 哈囉 的各種誤辨
        "哈囉", "哈喽", "哈啰", "哈羅", "哈洛", "哈漏",
        "阿羅", "阿洛", "沙羅",
        # 組合
        "哈囉曼波", "哈囉漫波", "哈囉漫播", "哈囉慢播", "哈囉慢波", "哈囉滿波",
        "哈囉們波", "哈囉半波",
        "哈羅曼波", "哈洛曼波", "哈漏曼波",
        "羅曼波", "阿羅曼波",
        # 謝謝 的誤辨
        "謝謝曼波", "謝謝漫波", "謝謝漫播", "謝謝慢播",
        "谢谢曼波", "谢谢漫波",
    ]

    print(f"\n  目前熱詞清單（boost=20.0）：{SPEECH_CONTEXT_PHRASES}")
    print()

    covered = []
    not_covered = []

    for output in possible_asr_outputs:
        # 檢查是否被任何熱詞包含或被任何熱詞包含
        is_covered = False
        for phrase in SPEECH_CONTEXT_PHRASES:
            # 熱詞是否是輸出的子串，或輸出是否包含熱詞
            if phrase in output or output in phrase:
                is_covered = True
                break
            # 也檢查「曼波」類的核心詞是否匹配
            core_variants = ["曼波", "漫波", "漫播", "慢播"]
            for cv in core_variants:
                if cv in output and cv == phrase:
                    is_covered = True
                    break

        if is_covered:
            covered.append(output)
        else:
            not_covered.append(output)

    # 即使不在熱詞清單中，也檢查 WAKE_WORDS 和 END_WORDS 能否匹配
    wake_covered = []
    end_covered = []
    still_uncovered = []

    for output in not_covered:
        if check_wake_match(output):
            wake_covered.append(output)
        elif check_end_match(output):
            end_covered.append(output)
        else:
            still_uncovered.append(output)

    print(f"  熱詞直接覆蓋: {len(covered)}/{len(possible_asr_outputs)}")
    print(f"  _MAMBO_VARIANTS 彌補: {len(wake_covered)}")
    print(f"  END_WORDS 彌補: {len(end_covered)}")
    print(f"  仍未覆蓋: {len(still_uncovered)}")

    if still_uncovered:
        print(f"\n  ⚠️ 以下 ASR 輸出不在熱詞清單中，也無法被 _MAMBO_VARIANTS/END 詞匹配：")
        for output in still_uncovered:
            print(f"    - 「{output}」")

    # 建議新增的熱詞
    suggested = set()
    for output in still_uncovered:
        # 提取核心變體
        for variant in ["曼波", "漫波", "漫播", "慢播", "慢波", "滿波", "們波",
                        "哈囉", "哈羅", "哈洛", "哈漏"]:
            if variant in output and variant not in SPEECH_CONTEXT_PHRASES:
                suggested.add(variant)

    if suggested:
        print(f"\n  💡 建議在 speech_contexts 中新增以下熱詞：")
        for s in sorted(suggested):
            print(f"    - \"{s}\"")

    total_covered = len(covered) + len(wake_covered) + len(end_covered)
    total = len(possible_asr_outputs)
    coverage = total_covered / total * 100 if total > 0 else 0

    print(f"\n  📊 熱詞+匹配邏輯總覆蓋率: {total_covered}/{total} = {coverage:.1f}%")

    return {"covered": len(covered), "wake": len(wake_covered),
            "end": len(end_covered), "uncovered": still_uncovered,
            "total": total, "rate": coverage, "suggested": suggested}


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 4：日常對話中不應誤觸發的場景
# ═══════════════════════════════════════════════════════════════════════════════

def test_false_positive_rejection():
    print("=" * 70)
    print("測試 4：日常對話中的觸發行為 — 含曼波→觸發，不含→拒絕")
    print("=" * 70)

    test_cases = [
        # ── 含「曼波」的日常對話 → 新邏輯下會觸發（關鍵字就是曼波）──
        ("曼波舞很好看", True, "日常-含曼波→觸發"),
        ("跳曼波", True, "日常-含曼波→觸發"),
        ("曼波舞蹈", True, "日常-含曼波→觸發"),
        ("我喜歡曼波", True, "日常-含曼波→觸發"),
        ("播放曼波音樂", True, "日常-含曼波→觸發"),
        ("什麼是曼波", True, "日常-含曼波→觸發"),
        ("曼波是什麼", True, "日常-含曼波→觸發"),

        # ── 不含「曼波」的打招呼 → 不觸發 ──
        ("你好世界", False, "打招呼-無曼波"),
        ("大家好", False, "打招呼-無曼波"),
        ("哈囉世界", False, "哈囉但無曼波→不觸發"),
        ("哈囉你好", False, "哈囉但無曼波→不觸發"),

        # ── 其他含「波」的詞但無曼波 → 不觸發 ──
        ("波浪", False, "含波但無曼波"),
        ("波士頓", False, "含波但無曼波"),
        ("波蘭", False, "含波但無曼波"),
    ]

    passed = 0
    failed = 0
    results = []

    for text, expected, desc in test_cases:
        matched = check_wake_match(text)
        ok = (matched == expected)

        if not ok:
            status = "⚠️" if matched and not expected else "❌"
            print(f"  {status} 「{text}」({desc})")
            print(f"     預期: {'匹配' if expected else '不匹配'}, 實際: {'匹配' if matched else '不匹配'}")
            failed += 1
        else:
            passed += 1

        results.append({"text": text, "expected": expected, "actual": matched, "passed": ok, "desc": desc})

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 誤觸發拒絕率: {passed}/{len(test_cases)} = {rate:.1f}%")
    if rate >= 80:
        print(f"  ✅ 誤觸發控制良好（≥80%）")
    else:
        print(f"  ⚠️ 誤觸發率偏高，建議調整 _MAMBO_VARIANTS")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 5：s2t 轉換對曼波匹配的影響
# ═══════════════════════════════════════════════════════════════════════════════

def test_s2t_mambo():
    print("=" * 70)
    print("測試 5：簡→繁轉換對曼波匹配的影響")
    print("=" * 70)

    test_cases = [
        # (簡體 ASR 輸出, 轉換後預期, 是否應匹配喚醒詞)
        ("哈喽曼波", "哈囉曼波", True),
        ("哈喽漫播", "哈囉漫播", True),
        ("哈喽慢播", "哈囉慢播", True),
        ("谢谢曼波", "謝謝曼波", True),  # 含曼波→觸發（同時也是結束詞）
        ("谢谢漫播", "謝謝漫播", True),  # 含漫播→觸發
    ]

    passed = 0
    failed = 0

    for simp, expected_trad, expected_wake in test_cases:
        trad = _s2t(simp)
        trad_ok = trad == expected_trad
        wake_ok = check_wake_match(simp) == expected_wake
        ok = trad_ok and wake_ok

        if not ok:
            print(f"  ❌ 「{simp}」→「{trad}」(預期「{expected_trad}」)")
            if not trad_ok:
                print(f"     轉換不正確！")
            if not wake_ok:
                actual = check_wake_match(simp)
                print(f"     喚醒匹配: 實際={actual}, 預期={expected_wake}")
            failed += 1
        else:
            passed += 1

    rate = passed / len(test_cases) * 100
    print(f"\n  📊 s2t 曼波轉換正確率: {passed}/{len(test_cases)} = {rate:.1f}%")

    return {"passed": passed, "total": len(test_cases), "rate": rate}


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  曼波喚醒詞 / 結束詞 / 熱詞 反覆測試                       ║")
    print("║  驗證所有可能的 ASR 輸出變體和誤辨場景                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # 印出目前設定
    print(f"  WAKE_WORDS ({len(WAKE_WORDS)}): {sorted(WAKE_WORDS)}")
    print(f"  END_WORDS ({len(END_WORDS)}): {sorted(END_WORDS)}")
    print(f"  _MAMBO_VARIANTS: {_MAMBO_VARIANTS}")
    print(f"  SPEECH_CONTEXT_PHRASES ({len(SPEECH_CONTEXT_PHRASES)}): {SPEECH_CONTEXT_PHRASES}")
    print()

    # 測試 1：喚醒詞
    wake_results = test_wake_word_variants()
    wake_pass = sum(1 for r in wake_results if r["passed"])
    wake_total = len(wake_results)
    print()

    # 測試 2：結束詞
    end_results = test_end_word_variants()
    end_pass = sum(1 for r in end_results if r["passed"])
    end_total = len(end_results)
    print()

    # 測試 3：熱詞覆蓋率
    context_result = test_speech_context_coverage()
    print()

    # 測試 4：誤觸發拒絕
    fp_results = test_false_positive_rejection()
    fp_pass = sum(1 for r in fp_results if r["passed"])
    fp_total = len(fp_results)
    print()

    # 測試 5：s2t 轉換
    s2t_result = test_s2t_mambo()
    print()

    # ═══ 最終總結 ═══
    print("=" * 70)
    print("📊 曼波關鍵字反覆測試總結")
    print("=" * 70)

    print(f"\n  1. 喚醒詞變體覆蓋率:   {wake_pass}/{wake_total} = {wake_pass/wake_total*100:.1f}%")
    print(f"  2. 結束詞變體覆蓋率:   {end_pass}/{end_total} = {end_pass/end_total*100:.1f}%")
    print(f"  3. 熱詞+匹配總覆蓋率:  {context_result['rate']:.1f}%")
    if context_result["suggested"]:
        print(f"     建議新增熱詞: {sorted(context_result['suggested'])}")
    print(f"  4. 誤觸發拒絕率:       {fp_pass}/{fp_total} = {fp_pass/fp_total*100:.1f}%")
    print(f"  5. s2t 曼波轉換:       {s2t_result['rate']:.1f}%")

    all_pass = (
        wake_pass == wake_total and
        end_pass == end_total and
        fp_pass == fp_total  # 新邏輯下含曼波→觸發，不含→拒絕，全部應通過
    )

    print()
    if all_pass:
        print("✅ 曼波關鍵字反覆測試通過！")
    else:
        print("⚠️ 部分測試需要調整")

    # 詳細建議
    print()
    print("═" * 70)
    print("📋 詳細分析")
    print("═" * 70)

    # 分析 _MAMBO_VARIANTS 的觸發行為
    false_positives = [r for r in fp_results if r["actual"] and not r["expected"]]
    if false_positives:
        print(f"\n  ⚠️ _MAMBO_VARIANTS 觸發但預期不觸發（{len(false_positives)} 條）：")
        for r in false_positives:
            print(f"    - 「{r['text']}」({r['desc']})")
        print(f"  說明：_MAMBO_VARIANTS 以「曼波」為關鍵字，任何含「曼波」的文字都會觸發。")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
