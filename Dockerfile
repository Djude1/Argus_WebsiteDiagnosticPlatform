# 使用官方 Playwright Python 映像（已預裝 Chromium 於 /ms-playwright，與主機隔離）
# 版本必須與 pyproject.toml 內 playwright 套件版本相符，否則 BrowserType.launch 會找不到 chromium 執行檔
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

WORKDIR /app

# 在 image 內安裝 uv；不污染主機環境
RUN pip install --no-cache-dir uv==0.9.17

# 先複製依賴定義，利用 layer cache 加速重複 build
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

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
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && nuclei -update-templates -silent || true

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

# 預設啟動 Django runserver；docker-compose 會視服務覆寫此 command
# 注意：runserver 僅適合開發；正式部署需改用 gunicorn 並關閉 DEBUG
CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
