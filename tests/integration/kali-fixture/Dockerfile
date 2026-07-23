# ⚠️ 警告：本 image 是刻意脆弱的 Argus Kali SQLmap 整合測試靶機。
# 永遠不可 push 到任何公開 registry、不可部署到「整合測試用的臨時 kind workflow」
# 以外的任何環境（包含 dev / staging / production）。詳見 app.py 的警告標頭。
#
# 使用 python:3.12-slim 純 stdlib runtime，不需任何第三方套件。
FROM python:3.12-slim@sha256:df850115c2e8a00e992a1f0ae9e51d5e8b8e4e7b8e4c7d0e4a1e4d5c8b6a4e2f

WORKDIR /app
COPY app.py /app/app.py

# 容器以 root 啟動 sqlite 會在 /tmp 寫入；run 為非 root 時，/tmp 由 Docker 預設開放。
RUN python -c "import sqlite3; sqlite3.connect('/tmp/probe.db').close()" \
    && rm -f /tmp/probe.db

EXPOSE 8080
# 直接執行 app.py；init_db 會在啟動時建立 /tmp/argus-fixture.db。
CMD ["python", "/app/app.py"]
