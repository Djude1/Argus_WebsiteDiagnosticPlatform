#!/bin/sh

echo "=== 等待資料庫就緒 ==="
while ! python -c "
import psycopg2, os, sys
try:
    psycopg2.connect(
        dbname=os.environ['POSTGRES_DB'],
        user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'],
        host=os.environ.get('DB_HOST', 'db'),
        port=os.environ.get('DB_PORT', '5432')
    )
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    echo "資料庫尚未就緒，1秒後重試..."
    sleep 1
done
echo "資料庫已就緒！"

echo "=== 建立遷移檔案 ==="
python manage.py makemigrations accounts products orders team content analytics --noinput

echo "=== 執行資料庫遷移 ==="
python manage.py migrate --noinput

echo "=== 收集靜態檔案 ==="
python manage.py collectstatic --noinput

echo "=== 建立超級管理員（若不存在）==="
python manage.py shell -c "
from accounts.models import CustomUser
import os
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '1124')
if not CustomUser.objects.filter(username=username).exists():
    CustomUser.objects.create_superuser(username=username, email=email, password=password, role='superadmin')
    print(f'超級管理員 {username} 建立成功')
else:
    # 若帳號已存在，確保所有超級管理員屬性正確
    u = CustomUser.objects.get(username=username)
    changed = False
    if u.role != 'superadmin':
        u.role = 'superadmin'
        changed = True
    if not u.is_superuser:
        u.is_superuser = True
        changed = True
    if not u.is_staff:
        u.is_staff = True
        changed = True
    if not u.check_password(password):
        u.set_password(password)
        changed = True
    if changed:
        u.save()
        print(f'已更新超級管理員 {username} 的設定')
    else:
        print(f'超級管理員 {username} 已存在且設定正確，跳過')
"

echo "=== 建立初始資料（產品、功能等）==="
python manage.py shell -c "
from products.models import Product, ProductFeature, ProductSpec
import os, shutil

# 確保模型目錄存在
os.makedirs('media/models', exist_ok=True)

# 建立 AI 盲人輔助智慧眼鏡產品（研究型專案）
if not Product.objects.filter(name='AI 盲人輔助智慧眼鏡').exists():
    product = Product.objects.create(
        name='AI 盲人輔助智慧眼鏡',
        short_description='專為視障人士設計的 AI 智慧眼鏡，結合影像 AI 與語音互動，守護每一步行走',
        description='''AI 盲人輔助智慧眼鏡是一款專為視障人士設計的智慧穿戴裝置，整合 YOLO 即時影像辨識、Lucas-Kanade 光流導航演算法與大型語言模型，提供全方位的視障輔助功能。

系統以 Seeed Studio XIAO ESP32S3 為核心硬體，透過 WebSocket 與 Python FastAPI 伺服器即時通訊。攝影機串流影像至後端進行 YOLO 推理，語音透過 Groq Whisper 辨識後由 Gemini 2.5 Flash 處理，TTS 合成語音回應再播放至使用者耳機。

主要功能包括：盲道即時導航（YOLO 分割 + 光流偵測）、斑馬線過馬路輔助（等待紅綠燈）、障礙物偵測迴避、物品尋找模式（YOLOE 開放詞彙）與自然語音 AI 對話。本專案基於開源專案 OpenAIglasses_for_Navigation 開發，為學術研究用途，不進行商業販售。''',
        price=0,
        original_price=0,
        stock=50,
        model_3d='models/aiglass.glb',
        is_active=True
    )

    features = [
        ('🦯 盲道導航', '利用 YOLO 分割模型即時偵測盲道，透過 Lucas-Kanade 光流計算行走方向，語音引導使用者正確行走', '🦯'),
        ('🚦 斑馬線輔助', '自動辨識斑馬線與交通號誌，偵測紅綠燈狀態，等待綠燈後語音提示使用者安全過馬路', '🚦'),
        ('🔍 物品尋找', '使用者語音說出目標物品名稱，YOLOE 開放詞彙模型進行偵測，語音回報物品位置與距離', '🔍'),
        ('🎙️ 語音 AI', 'Groq Whisper 語音辨識 + Gemini 2.5 Flash 自然語言處理，支援流暢中文語音對話互動', '🎙️'),
        ('📡 即時串流', 'ESP32S3 透過 WebSocket 即時串流影像與音訊，Python FastAPI 後端毫秒級 AI 推理回應', '📡'),
        ('🛡️ 障礙物偵測', 'YOLOE 多類別障礙物即時偵測，自動提醒前方障礙物類型與位置，防止碰撞意外', '🛡️'),
    ]
    for title, desc, icon in features:
        ProductFeature.objects.create(product=product, title=title, description=desc, icon=icon)

    specs = [
        ('主控晶片', 'Seeed XIAO ESP32S3'),
        ('攝影機', 'OV2640 1080p DVP'),
        ('麥克風', 'PDM 數位麥克風'),
        ('喇叭', 'MAX98357A I2S 功放'),
        ('IMU', 'ICM42688 六軸感測器'),
        ('連線方式', 'Wi-Fi 802.11 b/g/n'),
        ('後端框架', 'Python FastAPI'),
        ('AI 推理', 'YOLOv8 / YOLOE 本地'),
        ('語音辨識', 'Groq Whisper Large v3'),
        ('語音合成', 'Gemini TTS Flash'),
    ]
    for key, value in specs:
        ProductSpec.objects.create(product=product, key=key, value=value)

    print('初始產品資料建立成功')
else:
    print('產品資料已存在，跳過')
"

echo "=== 初始化網站內容（Singleton 模型）==="
python manage.py shell -c "
from content.models import (
    SiteSettings, HomeContent, ProductPageContent,
    DownloadPageContent, DownloadFeature, DownloadStep,
    PurchasePageContent, TeamPageContent,
)

# 載入所有 Singleton 模型（自動建立預設值）
SiteSettings.load()
HomeContent.load()
ProductPageContent.load()
DownloadPageContent.load()
PurchasePageContent.load()
TeamPageContent.load()
print('Singleton 內容模型初始化完成')

# 建立 APP 功能特色
if not DownloadFeature.objects.exists():
    features = [
        ('M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0', 'Wi-Fi 藍牙配對', '快速連線智慧眼鏡，穩定傳輸語音與導航指令'),
        ('M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7', '即時導航控制', '在手機端設定目的地，即時同步至眼鏡 AR 顯示'),
        ('M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z', 'AI 語音設定', '調整 OpenAI API 金鑰、語音喚醒詞與回應語言'),
        ('M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z', '使用數據儀表板', '查看電池電量、使用時長與 AI 互動紀錄'),
        ('M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15', '韌體 OTA 更新', '一鍵更新眼鏡韌體，隨時保持最新功能'),
        ('M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z', '隱私安全管理', '本地化資料處理，麥克風與鏡頭權限完全透明'),
    ]
    for i, (svg, title, desc) in enumerate(features):
        DownloadFeature.objects.create(icon_svg=svg, title=title, description=desc, order=i)
    print('APP 功能特色初始化完成')
else:
    print('APP 功能特色已存在，跳過')

# 建立安裝步驟
if not DownloadStep.objects.exists():
    steps = [
        ('01', '下載並安裝 APK', '點擊下方按鈕下載 APK 檔案，在 Android 系統設定中允許「未知來源」後安裝。'),
        ('02', '開啟 APP 並配對眼鏡', '確保眼鏡已開機並處於配對模式（長按電源鍵 3 秒），APP 將自動搜尋附近的裝置。'),
        ('03', '輸入 OpenAI API 金鑰', '前往 APP 設定頁面，填入您的 OpenAI API 金鑰以啟用 AI 語音助理功能。'),
        ('04', '開始使用', '說出喚醒詞「Hey AI」，即可開始使用導航與語音助理功能。'),
    ]
    for i, (num, title, desc) in enumerate(steps):
        DownloadStep.objects.create(step_number=num, title=title, description=desc, order=i)
    print('安裝步驟初始化完成')
else:
    print('安裝步驟已存在，跳過')
"

echo "=== 建立初始團隊成員資料 ==="
python manage.py shell -c "
from team.models import TeamMember

if not TeamMember.objects.exists():
    # 原專案參考者（佔位符，等使用者填入正確資訊）
    TeamMember.objects.create(
        name='AI-FanGe',
        member_type='reference',
        role='原專案作者',
        bio='OpenAIglasses_for_Navigation 開源專案創作者，致力於將 AI 技術融入日常穿戴裝置。',
        github_url='https://github.com/AI-FanGe',
        order=1
    )
    # 開發團隊成員（佔位符）
    members = [
        ('成員一', '全端開發 / 專題負責人'),
        ('成員二', '前端開發 / UI 設計'),
        ('成員三', '後端開發 / 資料庫'),
        ('成員四', '3D 建模 / 硬體整合'),
    ]
    for i, (name, role) in enumerate(members, start=1):
        TeamMember.objects.create(
            name=name,
            member_type='developer',
            role=role,
            bio='請至後台管理介面修改此成員的個人介紹。',
            order=i
        )
    print('初始團隊成員建立成功')
else:
    print('團隊成員已存在，跳過')
"

echo "=== 載入 Fixtures 初始資料（若存在）==="
if [ -f fixtures/initial_data.json ]; then
    python manage.py loaddata fixtures/initial_data.json 2>/dev/null && echo "Fixtures 載入成功" || echo "Fixtures 載入失敗或資料已存在，跳過"
else
    echo "未找到 fixtures/initial_data.json，跳過"
fi

echo "=== 啟動 Gunicorn 伺服器 ==="
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
