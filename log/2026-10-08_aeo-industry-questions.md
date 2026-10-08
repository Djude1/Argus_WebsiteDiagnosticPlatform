# AEO 同業常見問句：付款方式與預約（roadmap §2 AEO 第 5 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- **先標註再寫規則**：回歸資料集（`aeo/gold_dataset.py`）新增 9 個案例，寫規則前先標註。
  - 調整集 5 個：
    - 電商付款方式寫清楚 → 可回答。
    - 付款只叫人洽客服 → 資訊不足。
    - 只有訂單查詢 → 無答案。
    - 診所線上預約與電話 → 可回答。
    - 咖啡店只說包場要預約 → 資訊不足。
  - 保留集 4 個：
    - 健身房繳費方式 → 可回答。
    - 餐廳訂位方式 → 可回答。
    - 只寫採預約制 → 資訊不足。
    - 結帳只談優惠券 → 無答案。
- `aeo/questions.py` 新增兩個意圖：
  - `payment`「可以使用哪些付款方式？」，答案型態 `PAYMENT`。
  - `booking`「如何預約或訂位？」，答案型態 `BOOKING`。
  - 兩者都有觸發詞與主題詞（`anchors`）。只寫「結帳時可用優惠券」不算在講付款。
- `aeo/answers.py`：
  - `_PAYMENT_METHOD`：信用卡、ATM、轉帳、LINE Pay、街口、貨到付款、現金、credit card 等。可信度「確認」，因為答案值逐字出現在原文。
  - `_BOOKING_CHANNEL`：線上預約、預約系統、表單、LINE、來電、撥打、電話號碼、點選、填寫等。可信度「可能」。
- **依真實網站核對修正**：
  - 選單連結文字不觸發、也不當答案。ntub.edu.tw 的「出納付款查詢」「心理諮商線上預約」原本讓學校網站被問付款與預約。
    - 改法：這兩題的觸發詞只算小標題與 ≥15 字的段落，判定也只看 ≥15 字的段落。
    - 曾暫時把付款觸發門檻提高到 3，結果保留集的健身房案例不出題；連結文字的問題已由上一點解決，所以改回 2。
  - inline.app 的「pay online by credit card」原本判資訊不足：補英文付款方式。
  - 不算預約管道：
    - 「inline」單獨出現（英文單字）。
    - 平台名稱 EZTABLE（eztable.com 的「EZTABLE 有權取消此訂單」原本被當成預約管道）。
- **不做**「從一般小標題自動造題」：該小標題下的段落本身就是答案，幾乎一定判成可回答，只會灌高分數。網站自己以問號結尾的小標題原本就會出題。
- 文件：scans CLAUDE.md、roadmap、需求書 AEO 段落。

## 量測（`manage.py aeo_benchmark`）
- 改前：48 站 70 題，accuracy 0.971、precision 1.0、recall 0.974、保留集 19／21。
- 改後：57 站 79 題，accuracy 0.975、precision 1.0、recall 0.977、保留集 23／25。新增保留集 4／4 一次判對。
- 仍不一致的 2 題是改前就有的：建置中網站的介紹題、民宿房價題沒有出題。

## 真實網站核對
- mackay.org.tw：預約可回答（「參觀日至少 2 週前完成線上預約申請」）。
- inline.app：付款可回答（credit card）；預約資訊不足（只有「Booking management」）。
- eztable.com：付款可回答；預約資訊不足。
- ntub.edu.tw、ntubimdbirc.tw、cna.com.tw、setn.com、wordpress.org：不出這兩題。

## 影響範圍
- 正文確實談到付款或預約的網站，AEO 多 1–2 題，會影響 AEO 分數；沒寫付款方式或預約管道的會列為資訊不足或無答案。
- `RULESET_VERSION` 今天已是 2026.10.08；不需要 migration。

## 驗證方式
- `aeo_benchmark` 通過門檻。
- 新測試 `tests_aeo_industry_questions.py`（4 項）：英文付款方式、選單連結不出題、平台名稱與 inline 不算預約管道、LINE 與電話預約。
- 全套後端測試、`ruff check backend`。
