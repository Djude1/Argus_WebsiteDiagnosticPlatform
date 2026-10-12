import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FrontendPrerenderContractTest(unittest.TestCase):
    """公開頁建置時預先渲染成 <路徑>.html（frontend/scripts/prerender.mjs）。

    兩份 nginx 設定（image 內建與 K8s ConfigMap）都要提供這些檔案。
    """

    def _configs(self):
        return {
            "frontend/nginx.conf": (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8"),
            "k8s/05-frontend.yaml": (ROOT / "k8s" / "05-frontend.yaml").read_text(encoding="utf-8"),
        }

    def test_nginx_serves_prerendered_pages(self):
        for name, conf in self._configs().items():
            with self.subTest(name):
                self.assertIn("try_files $uri $uri.html $uri/ /index.html;", conf)
                self.assertIn("rewrite ^ /root.html last;", conf)

    def test_build_script_prerenders(self):
        package = (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
        self.assertIn("node scripts/prerender.mjs", package)


if __name__ == "__main__":
    unittest.main()
