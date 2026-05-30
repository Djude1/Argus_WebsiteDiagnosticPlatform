/**
 * ============================================
 * YOLO 日常物品辨識系統 - ESP32 端
 * ============================================
 * 硬體：XIAO ESP32-S3 Sense
 * 攝影機：TY-OV3660-75MM-V2.0 (OV3660 3MP)
 * 功能：HTTP MJPEG 影像串流
 * 
 * 使用方式：
 * 1. 燒錄此程式到 ESP32
 * 2. 開啟序列監視器查看 IP 位址
 * 3. 瀏覽器開啟 http://[ESP32_IP]/stream
 * 4. Python 端使用此 URL 接收影像
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include "camera_pins.h"
#include "config.h"

// ============================================
// 全域變數
// ============================================
WebServer server(HTTP_SERVER_PORT);
bool cameraReady = false;
unsigned long lastFrameTime = 0;
int frameCount = 0;

// ============================================
// 攝影機初始化
// ============================================
bool initCamera() {
    camera_config_t config;
    
    // 基本設定
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    
    // GPIO 腳位設定 (XIAO ESP32-S3 Sense + OV3660)
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sscb_sda = SIOD_GPIO_NUM;
    config.pin_sscb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    
    // 時鐘與格式設定
    config.xclk_freq_hz = XCLK_FREQ_HZ;
    config.pixel_format = PIXFORMAT_JPEG;  // 直接輸出 JPEG 格式
    
    // 影像品質設定 (需 PSRAM 支援)
    config.frame_size = FRAME_SIZE;        // 解析度
    config.jpeg_quality = JPEG_QUALITY;    // JPEG 品質
    config.fb_count = FB_COUNT;            // 緩衝區數量
    
    // 初始化攝影機
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        DEBUG_PRINTF("攝影機初始化失敗: 0x%x", err);
        return false;
    }
    
    // 取得感光器資訊
    sensor_t *s = esp_camera_sensor_get();
    if (s != NULL) {
        DEBUG_PRINTF("感光器 ID: 0x%x", s->id.PID);
        
        // OV3660 特定設定
        if (s->id.PID == OV3660_PID) {
            DEBUG_PRINT("偵測到 OV3660 感光器");
            
            // 調整影像參數
            s->set_brightness(s, 0);      // 亮度 -2 到 2
            s->set_contrast(s, 0);        // 對比 -2 到 2
            s->set_saturation(s, 0);      // 飽和度 -2 到 2
            s->set_sharpness(s, 0);       // 銳利度 -2 到 2
            s->set_whitebal(s, 1);        // 自動白平衡
            s->set_awb_gain(s, 1);        // 自動白平衡增益
            s->set_exposure_ctrl(s, 1);   // 自動曝光
            s->set_aec2(s, 1);            // 自動曝光 DSP
            s->set_ae_level(s, 0);        // 曝光等級 -2 到 2
            s->set_gain_ctrl(s, 1);       // 自動增益
            s->set_agc_gain(s, 0);        // AGC 增益
            s->set_gainceiling(s, (gainceiling_t)0);  // 增益上限
            s->set_colorbar(s, 0);        // 關閉測試條紋
        }
    }
    
    DEBUG_PRINT("攝影機初始化成功");
    return true;
}

// ============================================
// WiFi 連線
// ============================================
bool connectWiFi() {
    DEBUG_PRINT("連接 WiFi 中...");
    DEBUG_PRINTF("SSID: %s", WIFI_SSID);
    
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    WiFi.setSleep(false);  // 關閉 WiFi 睡眠模式以提高穩定性
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        DEBUG_PRINT("\nWiFi 連線成功!");
        DEBUG_PRINTF("IP 位址: %s", WiFi.localIP().toString().c_str());
        DEBUG_PRINTF("訊號強度: %d dBm", WiFi.RSSI());
        
        // 啟動 mDNS 服務 (自動發現功能)
        if (MDNS.begin(MDNS_HOSTNAME)) {
            DEBUG_PRINT("mDNS 服務已啟動");
            DEBUG_PRINTF("主機名: %s.local", MDNS_HOSTNAME);
            // 註冊 HTTP 服務
            MDNS.addService(MDNS_SERVICE, MDNS_PROTOCOL, HTTP_SERVER_PORT);
        } else {
            DEBUG_PRINT("mDNS 啟動失敗!");
        }
        
        return true;
    } else {
        DEBUG_PRINT("\nWiFi 連線失敗!");
        return false;
    }
}

// ============================================
// HTTP 處理函式
// ============================================

// MJPEG 串流處理器
void handleStream() {
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    size_t jpg_buf_len = 0;
    uint8_t *jpg_buf = NULL;
    char part_buf[64];
    
    // 設定 HTTP 回應標頭
    res = server.sendHeader("Connection", "close");
    res = server.sendHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    res = server.sendHeader("Pragma", "no-cache");
    res = server.sendHeader("Expires", "0");
    res = server.sendHeader("Access-Control-Allow-Origin", "*");
    res = server.setContentLength(CONTENT_LENGTH_UNKNOWN);
    res = send(200, "multipart/x-mixed-replace; boundary=frame", "");
    
    if (res != ESP_OK) {
        return;
    }
    
    DEBUG_PRINT("開始 MJPEG 串流");
    
    while (true) {
        // 從攝影機取得畫面
        fb = esp_camera_fb_get();
        if (!fb) {
            DEBUG_PRINT("攝影機擷取失敗");
            res = ESP_FAIL;
            break;
        }
        
        jpg_buf_len = fb->len;
        jpg_buf = fb->buf;
        
        if (res == ESP_OK) {
            // 發送畫面邊界標記
            size_t hlen = snprintf(part_buf, 64, 
                "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", 
                jpg_buf_len);
            res = server.sendContent(part_buf, hlen);
        }
        
        if (res == ESP_OK) {
            // 發送 JPEG 資料
            res = server.sendContent((const char *)jpg_buf, jpg_buf_len);
        }
        
        if (res == ESP_OK) {
            // 發送結束標記
            res = server.sendContent("\r\n", 2);
        }
        
        // 釋放緩衝區
        esp_camera_fb_return(fb);
        fb = NULL;
        
        if (res != ESP_OK) {
            break;
        }
        
        frameCount++;
        
        // 檢查客戶端連線狀態
        if (!server.client().connected()) {
            DEBUG_PRINT("客戶端斷線");
            break;
        }
    }
    
    DEBUG_PRINT("結束 MJPEG 串流");
}

// 單張快照處理器
void handleSnapshot() {
    camera_fb_t *fb = esp_camera_fb_get();
    
    if (!fb) {
        server.send(500, "text/plain", "攝影機擷取失敗");
        DEBUG_PRINT("快照失敗");
        return;
    }
    
    server.sendHeader("Content-Type", "image/jpeg");
    server.sendHeader("Content-Length", String(fb->len));
    server.sendHeader("Connection", "close");
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.send(200, "image/jpeg", (const char *)fb->buf, fb->len);
    
    esp_camera_fb_return(fb);
    DEBUG_PRINT("快照已發送");
}

// 狀態查詢處理器
void handleStatus() {
    String json = "{";
    json += "\"status\":\"running\",";
    json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
    json += "\"rssi\":" + String(WiFi.RSSI()) + ",";
    json += "\"frameCount\":" + String(frameCount) + ",";
    json += "\"uptime\":" + String(millis() / 1000) + ",";
    json += "\"freeHeap\":" + String(ESP.getFreeHeap());
    json += "}";
    
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.send(200, "application/json", json);
}

// 404 處理器
void handleNotFound() {
    server.send(404, "text/plain", "404: Not Found");
}

// ============================================
// 設定 HTTP 路由
// ============================================
void setupServer() {
    // 串流端點
    server.on(STREAM_PATH, HTTP_GET, handleStream);
    
    // 快照端點
    server.on(SNAPSHOT_PATH, HTTP_GET, handleSnapshot);
    
    // 狀態端點
    server.on(STATUS_PATH, HTTP_GET, handleStatus);
    
    // 根目錄導向串流
    server.on("/", HTTP_GET, []() {
        String html = "<!DOCTYPE html><html><head>";
        html += "<title>ESP32 MJPEG Stream</title>";
        html += "<style>body{font-family:Arial;text-align:center;background:#1a1a2e;color:#eee;}";
        html += "img{max-width:100%;border:3px solid #4ecca3;border-radius:10px;}";
        html += "h1{color:#4ecca3;}</style></head><body>";
        html += "<h1>XIAO ESP32-S3 Sense</h1>";
        html += "<img src='/stream'>";
        html += "<p>OV3660 Camera Stream</p>";
        html += "</body></html>";
        server.send(200, "text/html", html);
    });
    
    // 404 處理
    server.onNotFound(handleNotFound);
    
    server.begin();
    DEBUG_PRINT("HTTP 伺服器已啟動");
}

// ============================================
// 主程式
// ============================================
void setup() {
    // 初始化序列埠
    Serial.begin(SERIAL_BAUD_RATE);
    Serial.setDebugOutput(true);
    delay(1000);
    
    DEBUG_PRINT("================================");
    DEBUG_PRINT("YOLO 日常物品辨識系統 - ESP32 端");
    DEBUG_PRINT("硬體: XIAO ESP32-S3 Sense");
    DEBUG_PRINT("攝影機: TY-OV3660-75MM-V2.0");
    DEBUG_PRINT("================================");
    
    // 初始化攝影機
    cameraReady = initCamera();
    if (!cameraReady) {
        DEBUG_PRINT("錯誤：攝影機初始化失敗！");
        while (1) {
            delay(1000);
        }
    }
    
    // 連接 WiFi
    if (!connectWiFi()) {
        DEBUG_PRINT("錯誤：WiFi 連線失敗！");
        while (1) {
            delay(1000);
        }
    }
    
    // 設定 HTTP 伺服器
    setupServer();
    
    DEBUG_PRINT("================================");
    DEBUG_PRINT("系統就緒！");
    DEBUG_PRINTF("串流 URL (IP): http://%s%s", 
                 WiFi.localIP().toString().c_str(), STREAM_PATH);
    DEBUG_PRINTF("串流 URL (mDNS): http://%s.local%s", 
                 MDNS_HOSTNAME, STREAM_PATH);
    DEBUG_PRINTF("快照 URL: http://%s%s", 
                 WiFi.localIP().toString().c_str(), SNAPSHOT_PATH);
    DEBUG_PRINTF("狀態 URL: http://%s%s", 
                 WiFi.localIP().toString().c_str(), STATUS_PATH);
    DEBUG_PRINT("================================");
}

void loop() {
    server.handleClient();
    delay(1);  // 給 WiFi 任務一些時間
}
