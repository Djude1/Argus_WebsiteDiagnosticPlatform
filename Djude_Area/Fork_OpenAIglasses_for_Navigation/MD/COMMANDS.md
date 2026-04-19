# 常用指令速查

## 主伺服器

```bash
# 啟動單一裝置（FastAPI，port 8081）
uv run python app_main.py

# 啟動多裝置（預設 4 台，port 8081～8084）
uv run python start_multi_device.py

# 只啟動 N 台裝置
uv run python start_multi_device.py --count 2

# 指定起始 port
uv run python start_multi_device.py --base-port 8081
```

## 開發輔助

```bash
# ESP32 模擬器（用電腦攝影機/麥克風/喇叭代替硬體，需先啟動主伺服器）
uv run python esp32_simulator.py
```

## 環境設定

```bash
# 安裝所有依賴（第一次或 pyproject.toml 有變更時）
uv sync

# 新增套件
uv add 套件名稱
```

## 測試腳本

```bash
uv run python test_cross_street_blindpath.py   # 盲道導航測試
uv run python test_traffic_light.py            # 紅綠燈偵測測試
uv run python test_recorder.py                 # 錄音功能測試
uv run python test_crosswalk_awareness.py      # 斑馬線偵測測試
uv run python test_yoloe_compare.py            # YOLO-E 模型效能比較
```

## Website（Docker）

```bash
# 進入 Website 目錄
cd Website

# 第一次啟動（建置 + 啟動，port 8888）
docker compose up --build

# 日常啟動
docker compose up -d

# 停止
docker compose down

# 查看即時 log
docker compose logs -f backend
docker compose logs -f frontend

# 重新建置（修改 Dockerfile 或 requirements.txt 後）
docker compose up --build

# 進入 Django shell
docker compose exec backend python manage.py shell

# 手動 migrate
docker compose exec backend python manage.py migrate
```

## 存取位址

| 服務 | 位址 |
|------|------|
| 裝置 1 監控頁面 | http://localhost:8081 |
| 裝置 2 監控頁面 | http://localhost:8082 |
| 裝置 3 監控頁面 | http://localhost:8083 |
| 裝置 4 監控頁面 | http://localhost:8084 |
| 網站（Docker） | http://localhost:8888 |
| 網站後台管理 | http://localhost:8888/admin/ |
| 裝置 1（透過 nginx） | http://localhost:8888/device/1/ |
