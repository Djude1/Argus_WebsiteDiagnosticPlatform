# ============================================
# Windows 環境設定腳本
# ============================================
# 執行此腳本以設定 Python 虛擬環境

Write-Host "================================" -ForegroundColor Cyan
Write-Host "YOLO 日常物品辨識系統 - 環境設定" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# 檢查 uv 是否安裝
Write-Host "`n檢查 uv 是否已安裝..." -ForegroundColor Yellow
try {
    $uvVersion = uv --version
    Write-Host "uv 已安裝: $uvVersion" -ForegroundColor Green
} catch {
    Write-Host "uv 未安裝，請先安裝 uv" -ForegroundColor Red
    Write-Host "安裝方式: pip install uv" -ForegroundColor Yellow
    exit 1
}

# 建立虛擬環境
Write-Host "`n建立虛擬環境..." -ForegroundColor Yellow
uv venv

# 啟動虛擬環境
Write-Host "`n啟動虛擬環境..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# 安裝依賴
Write-Host "`n安裝依賴套件..." -ForegroundColor Yellow
uv sync

# 建立 .env 檔案 (如果不存在)
if (-not Test-Path .env) {
    Write-Host "`n建立 .env 設定檔..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host ".env 已建立，請編輯此檔案填入實際值" -ForegroundColor Yellow
}

# 建立必要目錄
Write-Host "`n建立必要目錄..." -ForegroundColor Yellow
$directories = @(
    "data/database",
    "data/datasets/raw",
    "data/datasets/annotated",
    "data/exports",
    "logs",
    "screenshots",
    "models/pretrained",
    "models/custom"
)

foreach ($dir in $directories) {
    if (-not Test-Path $dir) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  建立: $dir" -ForegroundColor Gray
    }
}

Write-Host "`n================================" -ForegroundColor Cyan
Write-Host "環境設定完成！" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Cyan
Write-Host "`n下一步:" -ForegroundColor Yellow
Write-Host "1. 編輯 .env 檔案，填入 WiFi 和 ESP32 IP 設定" -ForegroundColor White
Write-Host "2. 將 esp32/yollo_E.ino 燒錄到 ESP32" -ForegroundColor White
Write-Host "3. 執行: uv run python src/main.py --source esp32" -ForegroundColor White
Write-Host "`n查看 ESP32 IP 位址: 開啟序列監視器 (115200 baud)" -ForegroundColor Gray
