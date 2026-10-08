# 使用官方 Playwright Python 映像（已預裝 Chromium 於 /ms-playwright，與主機隔離）
# 版本必須與 pyproject.toml 內 playwright 套件版本相符，否則 BrowserType.launch 會找不到 chromium 執行檔
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

WORKDIR /app

# 在 image 內安裝 uv；不污染主機環境
RUN pip install --no-cache-dir uv==0.9.17

# 先複製依賴定義，利用 layer cache 加速重複 build
COPY pyproject.toml uv.lock ./

ENV UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
# 報告圖表用 matplotlib 繪製，需要 CJK 字型才不會把中文畫成一整排 □。
# 缺字型時 report_render/theme.py 會直接 RuntimeError（刻意大聲失敗——退回預設
# 字型的話報告照樣產出、照樣寄給客戶，沒有人會發現圖表中文全是方塊）。
# 報告對外只提供 PDF：排版產生的 .docx 由 LibreOffice Writer（無 GUI 版）轉檔，
# 見 backend/apps/scans/report_pdf.py。soffice --version 讓缺套件時 build 直接失敗。
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk \
    libreoffice-writer-nogui \
    && rm -rf /var/lib/apt/lists/* \
    && soffice --version

# 安裝 ProjectDiscovery 資安工具（Nuclei + Katana）
ARG NUCLEI_VERSION=3.8.0
ARG KATANA_VERSION=1.1.2
RUN apt-get update && apt-get install -y --no-install-recommends unzip wget \
    && wget -q "https://github.com/projectdiscovery/nuclei/releases/download/v${NUCLEI_VERSION}/nuclei_${NUCLEI_VERSION}_linux_amd64.zip" -O /tmp/nuclei.zip \
    && unzip /tmp/nuclei.zip nuclei -d /usr/local/bin/ \
    && chmod +x /usr/local/bin/nuclei \
    && wget -q "https://github.com/projectdiscovery/katana/releases/download/v${KATANA_VERSION}/katana_${KATANA_VERSION}_linux_amd64.zip" -O /tmp/katana.zip \
    && unzip /tmp/katana.zip katana -d /usr/local/bin/ \
    && chmod +x /usr/local/bin/katana \
    && rm /tmp/nuclei.zip /tmp/katana.zip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Nuclei 模板鎖定版本（模板治理，見 backend/apps/scans/nuclei_scanner.py）。
# 原本用 `nuclei -update-templates || true`：每次 build 拿到不同模板，下載失敗也照樣 build 成功，
# 掃描時沒有模板只會回報「0 項發現」。現在固定版本，並以模板庫自帶的 templates-checksum.txt
# 驗證每個模板內容（該檔本身以 sha256 鎖定）；任何一步失敗 build 就失敗。
# 升級模板：改這兩個 ARG（sha256 取新版 templates-checksum.txt），並確認 KEV 模板集的請求量。
ARG NUCLEI_TEMPLATES_VERSION=v10.4.9
ARG NUCLEI_TEMPLATES_CHECKSUM_SHA256=feff28857d327d25045f83f59013aa53cf9644ffecf78d3687d87d4370dba6f1
ENV ARGUS_NUCLEI_TEMPLATES_DIR=/opt/nuclei-templates
RUN mkdir -p /opt/nuclei-templates \
    && wget -q "https://github.com/projectdiscovery/nuclei-templates/archive/refs/tags/${NUCLEI_TEMPLATES_VERSION}.tar.gz" -O /tmp/nuclei-templates.tar.gz \
    && tar -xzf /tmp/nuclei-templates.tar.gz -C /opt/nuclei-templates --strip-components=1 \
    && rm /tmp/nuclei-templates.tar.gz \
    && cd /opt/nuclei-templates \
    && echo "${NUCLEI_TEMPLATES_CHECKSUM_SHA256}  templates-checksum.txt" | sha256sum -c --quiet - \
    && grep -v '^templates-checksum.txt:' templates-checksum.txt \
        | awk -F: '{h=$NF; sub(/:[^:]*$/,""); print h "  " $0}' | sha1sum -c --quiet - \
    && echo "${NUCLEI_TEMPLATES_VERSION}" > .argus-templates-version \
    && test "$(nuclei -duc -t /opt/nuclei-templates -tags kev -pt http -tl -silent 2>/dev/null | grep -c '\.yaml$')" -gt 100

# 安裝 docker CLI 靜態 binary（僅 client，無 daemon）
# 用途：worker 透過掛載的 host docker.sock 對 argus-kali-1 執行 docker exec（Phase 3 攻擊鏈）
# 僅 worker 服務會用到；web 服務雖也含此 binary 但不掛 socket，不會生效
ARG DOCKER_CLI_VERSION=27.3.1
RUN wget -q "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz" -O /tmp/docker.tgz \
    && tar -xzf /tmp/docker.tgz -C /tmp \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && chmod +x /usr/local/bin/docker \
    && rm -rf /tmp/docker /tmp/docker.tgz

# 複製後端原始碼
COPY backend ./backend

# Playwright 瀏覽器位於 image 內 /ms-playwright；與主機 .ms-playwright 各自獨立
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend
EXPOSE 8000

# 正式 image 預設使用 production WSGI server；開發模式由 docker-compose.dev.yml 覆寫。
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-"]
