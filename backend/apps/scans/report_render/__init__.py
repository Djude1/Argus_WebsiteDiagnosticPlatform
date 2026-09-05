"""argus_report — Argus 網站健檢報告 generator (data in, styled .docx out)."""
from .report import generate_report

# 排版版本。**改動任何會影響 .docx 版面的東西就要 +1**：新增/移除章節、
# 換圖表、改配色、改表格結構。views.py 用它判斷磁碟上的舊報告要不要重產——
# 沒有這個版本號時，掃描一旦產過報告就永遠拿不到新排版（使用者實際踩過：
# 修好圖表後重新下載舊掃描的報告，拿到的還是沒有圖表的快取檔，看起來像修復失敗）。
RENDERER_VERSION = 2

__all__ = ["generate_report", "RENDERER_VERSION"]
__version__ = "1.0.0"
