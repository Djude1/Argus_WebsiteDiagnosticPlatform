# 使用官方 Playwright Python 映像（已預裝 Chromium 於 /ms-playwright，與主機隔離）
# 版本必須與 pyproject.toml 內 playwright 套件版本相符，否則 BrowserType.launch 會找不到 chromium 執行檔
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

WORKDIR /app

# 在 image 內安裝 uv；不污染主機環境
RUN pip install --no-cache-dir uv==0.9.17

# 先複製依賴定義，利用 layer cache 加速重複 build
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

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
