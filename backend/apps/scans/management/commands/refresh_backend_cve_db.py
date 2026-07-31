"""管理命令：從 NVD 2.0 API 重新產生後端服務 CVE DB。

用法：
    uv run python backend/manage.py refresh_backend_cve_db [--api-key KEY]

以 ``virtualMatchString`` 逐產品（nginx/Apache/PHP）抓取所有 CVE，交由
``nvd_db.build_db_from_nvd`` 過濾轉換，寫入 ``security/data/backend_services.json``。

注意：
- 轉換邏輯（CPE 過濾 + 版本區間）已由 ``tests_nvd_db.py`` 的已知答案 fixture 鎖定；
  本命令只負責下載與寫檔。NVD API 查詢格式與速率限制請於首次手動執行時確認。
- 無 API key 時 NVD 限流 5 req/30s（預設每次請求間 6s）；有 key 則 50/30s（1s）。
  金鑰亦可由 ``NVD_API_KEY`` 環境變數提供。
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand

from apps.scans.security.nvd_db import TARGET_PRODUCTS, build_db_from_nvd
from apps.scans.security.service_cve_scanner import _DB_PATH

API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def _virtual_match_string(prefix: str) -> str:
    """CPE 前綴 → NVD virtualMatchString（完整 13 欄萬用形式）。"""
    # prefix 形如 "cpe:2.3:a:nginx:nginx:" → 補齊版本以後的 8 個萬用欄
    return prefix.rstrip(":") + ":*" * 8


class Command(BaseCommand):
    help = (
        "從 NVD 2.0 API 重新產生後端服務 CVE DB（nginx/Apache/PHP），"
        "寫入 security/data/backend_services.json。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--api-key",
            default=os.environ.get("NVD_API_KEY", ""),
            help="NVD API key（提升速率限制；亦可由 NVD_API_KEY 環境變數提供）",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=None,
            help="每次請求間隔秒數（預設：有 key 1s／無 key 6s）",
        )

    def handle(self, *args, **options):
        api_key = options["api_key"]
        sleep = options["sleep"] if options["sleep"] is not None else (1.0 if api_key else 6.0)
        all_cves: list[dict] = []
        for product, prefix in TARGET_PRODUCTS.items():
            self.stdout.write(f"抓取 {product}（{_virtual_match_string(prefix)}）…")
            collected = self._fetch_product(prefix, api_key, sleep)
            self.stdout.write(f"  {product}: 收集 {len(collected)} 個 CVE")
            all_cves.extend(collected)

        db = build_db_from_nvd(all_cves)
        counts = {p: len(d.get("vulnerabilities", [])) for p, d in db.items()}
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DB_PATH.write_text(
            json.dumps(db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.stdout.write(self.style.SUCCESS(f"寫入 {_DB_PATH}：{counts}"))

    def _fetch_product(self, prefix: str, api_key: str, sleep: float) -> list[dict]:
        out: list[dict] = []
        start = 0
        page = 2000
        while True:
            qs = urllib.parse.urlencode({
                "virtualMatchString": _virtual_match_string(prefix),
                "resultsPerPage": page,
                "startIndex": start,
            })
            headers = {"apiKey": api_key} if api_key else {}
            req = urllib.request.Request(f"{API_URL}?{qs}", headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.URLError as exc:
                self.stderr.write(self.style.ERROR(f"  NVD 請求失敗：{exc}"))
                break
            vulns = data.get("vulnerabilities") or []
            for v in vulns:
                cve = v.get("cve")
                if isinstance(cve, dict):
                    out.append(cve)
            total = data.get("totalResults") or 0
            start += page
            if start >= total or not vulns:
                break
            time.sleep(sleep)
        return out
