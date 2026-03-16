/**
 * ============================================
 * XIAO ESP32-S3 Sense 系統配置
 * ============================================
 */

#ifndef CONFIG_H
#define CONFIG_H

// ============================================
// WiFi 設定
// ============================================
// 注意：實際值請在燒錄前修改，或使用外部配置
#define WIFI_SSID       "HelloWorld"
#define WIFI_PASSWORD   "Aa0978926291"

// ============================================
// 伺服器設定
// ============================================
#define HTTP_SERVER_PORT        80
#define STREAM_PATH             "/stream"
#define SNAPSHOT_PATH           "/snapshot"
#define STATUS_PATH             "/status"

// ============================================
// mDNS 設定 (自動發現功能)
// ============================================
// ESP32 會廣播此主機名，可使用 http://yollo.local 連接
#define MDNS_HOSTNAME           "yollo"          // 主機名 (不含 .local)
#define MDNS_SERVICE            "http"           // 服務類型
#define MDNS_PROTOCOL           "tcp"            // 通訊協定

// ============================================
// 攝影機設定
// ============================================
// 解析度選項：FRAMESIZE_QVGA, FRAMESIZE_VGA, FRAMESIZE_SVGA, FRAMESIZE_XGA
#define FRAME_SIZE              FRAMESIZE_SVGA    // 800x600
#define JPEG_QUALITY            12                 // 0-63，數字越小品質越高
#define XCLK_FREQ_HZ            20000000          // 20MHz

// 緩衝區設定
#define FB_COUNT                2                  // 雙緩衝區 (提高穩定性)

// ============================================
// 序列埠設定
// ============================================
#define SERIAL_BAUD_RATE        115200

// ============================================
// LED 設定 (XIAO ESP32-S3 內建 RGB LED)
// ============================================
#define LED_PIN                 21                 // 內建 RGB LED
#define LED_BRIGHTNESS          50                 // 亮度 0-255

// ============================================
// 除錯設定
// ============================================
#define DEBUG_MODE              1                  // 1 = 開啟除錯輸出

#if DEBUG_MODE
    #define DEBUG_PRINT(x)      Serial.println(x)
    #define DEBUG_PRINTF(...)   Serial.printf(__VA_ARGS__)
#else
    #define DEBUG_PRINT(x)
    #define DEBUG_PRINTF(...)
#endif

#endif // CONFIG_H
