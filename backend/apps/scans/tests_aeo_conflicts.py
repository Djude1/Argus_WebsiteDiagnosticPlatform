"""AEO 內容衝突：價格、營業時間、客服專線（aeo/answers._value_conflict）。

roadmap §2 AEO 第 2 項。
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.aeo import answers as a
from apps.scans.aeo.content import Passage
from apps.scans.aeo.questions import INTENTS, Question


def _question(key: str) -> Question:
    intent = next(i for i in INTENTS if i.key == key)
    return Question(key=key, text=intent.question, answer_type=intent.answer_type,
                    keywords=intent.keywords, weight=intent.weight, source="intent")


def _p(url: str, text: str, heading: str = "") -> Passage:
    return Passage(page_url=url, index=0, text=text, heading=heading)


def _verdict(key: str, *passages: Passage, extra: tuple[Passage, ...] = ()) -> str:
    question = _question(key)
    candidates = list(passages)
    return a.judge(question, candidates, candidates + list(extra)).verdict


class PriceConflictTests(SimpleTestCase):
    def test_same_item_different_price_on_two_pages(self):
        self.assertEqual(_verdict(
            "price",
            _p("https://x.tw/a", "Python 入門課程學費 NT$4,800，共八週。"),
            _p("https://x.tw/b", "Python 入門課程學費 NT$5,200，報名後寄送連結。"),
        ), a.CONFLICT)

    def test_same_page_or_generic_label_is_not_conflict(self):
        # 同一頁的兩個價格：多半是不同方案
        self.assertEqual(_verdict(
            "price",
            _p("https://x.tw/a", "Python 入門課程學費 NT$4,800。"),
            _p("https://x.tw/a", "Python 入門課程學費 NT$5,200。"),
        ), a.ANSWERED)
        # 只有「學費」：不知道兩頁說的是不是同一門課
        self.assertEqual(_verdict(
            "price",
            _p("https://x.tw/a", "學費 NT$4,800。", heading="收費方式"),
            _p("https://x.tw/b", "學費 NT$6,000。", heading="收費方式"),
        ), a.ANSWERED)

    def test_qualified_prices_are_skipped(self):
        self.assertEqual(_verdict(
            "price",
            _p("https://x.tw/a", "Python 入門課程學費 NT$4,800。"),
            _p("https://x.tw/b", "Python 入門課程學費 NT$3,900。", heading="早鳥優惠"),
        ), a.ANSWERED)


class HoursAndPhoneConflictTests(SimpleTestCase):
    def test_hours_conflict_normalizes_times(self):
        self.assertEqual(_verdict(
            "hours",
            _p("https://x.tw/a", "營業時間：週一至週五 9:00-18:00，週末公休。"),
            _p("https://x.tw/b", "營業時間：週一至週五 10:00 至 19:00。"),
        ), a.CONFLICT)
        # 寫法不同但時間相同
        self.assertEqual(_verdict(
            "hours",
            _p("https://x.tw/a", "營業時間：週一至週五 9:00-18:00。"),
            _p("https://x.tw/b", "營業時間：週一至週五 09:00～18:00。"),
        ), a.ANSWERED)

    def test_multi_location_site_is_not_judged(self):
        self.assertEqual(_verdict(
            "hours",
            _p("https://x.tw/a", "營業時間：週一至週五 09:00-18:00。"),
            _p("https://x.tw/b", "營業時間：週一至週五 10:00-19:00。"),
            extra=(_p("https://x.tw/stores", "門市據點：信義、大安兩家門市。"),),
        ), a.ANSWERED)

    def test_only_hotlines_are_compared(self):
        self.assertEqual(_verdict(
            "contact_phone",
            _p("https://x.tw/a", "客服專線：02-2771-1234。"),
            _p("https://x.tw/b", "請撥打客服專線 (02) 2771-5678。"),
        ), a.CONFLICT)
        # 各單位電話本來就不同
        self.assertEqual(_verdict(
            "contact_phone",
            _p("https://x.tw/a", "系辦公室電話：02-2322-1111。"),
            _p("https://x.tw/b", "招生組電話：02-2322-2222。"),
        ), a.ANSWERED)
