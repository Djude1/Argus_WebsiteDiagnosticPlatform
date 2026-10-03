"""把 report_render 產生的 .docx 轉成 PDF（使用者下載與查驗都以 PDF 為準）。

排版仍由 report_render 以 Word 格式產生，再交給 LibreOffice headless 轉檔：
- 圖表、表格、頁首頁尾、浮水印都沿用同一套排版，不必再維護第二套 PDF 版面。
- 每次轉檔使用獨立的暫存使用者設定檔：LibreOffice 的設定檔有鎖，web 與 worker
  同時轉檔時共用設定檔會讓第二個行程直接結束而不產出檔案。
- 轉檔失敗一律拋 ReportConversionError，不退回提供 .docx（只提供 PDF 是產品決定）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings


class ReportConversionError(RuntimeError):
    """LibreOffice 不存在、逾時或沒有產出 PDF。"""


def _soffice_binary() -> str:
    binary = shutil.which("soffice") or shutil.which("libreoffice")
    if not binary:
        raise ReportConversionError("找不到 LibreOffice（soffice），無法產生 PDF 報告。")
    return binary


def convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> None:
    """把 docx_path 轉成 PDF 並原子寫入 pdf_path。"""
    timeout = getattr(settings, "ARGUS_REPORT_PDF_TIMEOUT_SECONDS", 120)
    with tempfile.TemporaryDirectory(prefix="argus-soffice-") as workdir:
        work = Path(workdir)
        command = [
            _soffice_binary(),
            f"-env:UserInstallation={(work / 'profile').as_uri()}",
            "--headless",
            "--norestore",
            "--nolockcheck",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(work),
            str(docx_path),
        ]
        try:
            subprocess.run(
                command, check=False, capture_output=True, timeout=timeout,
                env={**os.environ, "HOME": str(work)},
            )
        except subprocess.TimeoutExpired as exc:
            raise ReportConversionError(f"PDF 轉檔逾時（{timeout} 秒）。") from exc
        produced = work / f"{docx_path.stem}.pdf"
        if not produced.exists() or produced.stat().st_size == 0:
            raise ReportConversionError("LibreOffice 沒有產出 PDF。")
        # 先搬到目的目錄再 rename，下載中的使用者不會讀到寫一半的檔案
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        staging = pdf_path.with_name(f".{pdf_path.name}.tmp")
        shutil.move(str(produced), staging)
        os.replace(staging, pdf_path)
