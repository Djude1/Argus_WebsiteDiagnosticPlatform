@echo off
chcp 65001 >nul
echo ========================================
echo   AI 智慧眼鏡 - Flutter Android 建置
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] 清理舊檔案...
flutter clean

echo.
echo [2/3] 取得依賴...
flutter pub get

echo.
echo [3/3] 建置 Debug APK...
flutter build apk --debug

if errorlevel 1 (
    echo.
    echo [錯誤] 建置失敗！
    pause
    exit /b 1
)

echo.
echo ========================================
echo   建置成功！
echo ========================================
echo.
echo APK 位置：
echo   %cd%\build\app\outputs\flutter-apk\app-debug.apk
echo.
echo 安裝指令：
echo   adb install build\app\outputs\flutter-apk\app-debug.apk
echo.

pause
