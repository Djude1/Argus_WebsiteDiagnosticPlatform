"""argus_report — Argus 網站健檢報告 generator (data in, styled .docx out)."""
from .report import generate_report

# 排版版本。**改動任何會影響 .docx 版面的東西就要 +1**：新增/移除章節、
# 換圖表、改配色、改表格結構。views.py 用它判斷磁碟上的舊報告要不要重產——
# 沒有這個版本號時，掃描一旦產過報告就永遠拿不到新排版（使用者實際踩過：
# 修好圖表後重新下載舊掃描的報告，拿到的還是沒有圖表的快取檔，看起來像修復失敗）。
RENDERER_VERSION = 22  # 22：頁尾品牌改為「Argus AI網站健檢平台」；21：網站架構加「信任輪廓（五層）」一列；20：頁尾品牌改為「Argus 網站健檢平台」；19：掃描範圍加「檢測工具版本」；18：摘要「改一處就能一起解決」；17：附錄各分類扣分明細；16：資安發現標示類型（設定建議／曝露面／疑似弱點／已驗證弱點）；15：AEO 逐題可信度；14：AI 爬蟲政策；13：安全標頭等第（Mozilla Observatory 規則）；12：OWASP ZAP 被動分析的來源標示；11：PageSpeed Insights（Lighthouse／CrUX）；10：axe-core 無障礙發現的依據與來源；9：評分版本與跨版本比較；8：覆蓋契約（已解決只計確認修好、未完整完成的檢查）；7：部分掃描標示；6：網站優勢附依據、短章節不強制換頁、浮水印縮小；5：重新設計版面（字級層級、精簡低風險、網站概況）；4：改為只提供 PDF

__all__ = ["generate_report", "RENDERER_VERSION"]
__version__ = "1.0.0"
