#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

// --- 引腳定義 (XIAO ESP32-S3 Sense) ---
#define PWDN_GPIO_NUM -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 10
#define SIOD_GPIO_NUM 40
#define SIOC_GPIO_NUM 39
#define Y9_GPIO_NUM 48
#define Y8_GPIO_NUM 11
#define Y7_GPIO_NUM 12
#define Y6_GPIO_NUM 14
#define Y5_GPIO_NUM 16
#define Y4_GPIO_NUM 18
#define Y3_GPIO_NUM 17
#define Y2_GPIO_NUM 15
#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM 47
#define PCLK_GPIO_NUM 13

const char* ssid = "HelloWorld";
const char* password = "Aa0978926291";
const String relayServer = "http://10.139.219.157:5000/upload"; 

void setup() {
  Serial.begin(115200);
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM; config.pin_d1 = Y3_GPIO_NUM; config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM; config.pin_d4 = Y6_GPIO_NUM; config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM; config.pin_d7 = Y9_GPIO_NUM; config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM; config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM; config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM; config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM; config.xclk_freq_hz = 20000000;
  
  config.frame_size = FRAMESIZE_VGA;  // 高清模式
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 10;
  config.fb_count = 1;

  if (esp_camera_init(&config) != ESP_OK) return;

  // 正確修正畫面方向與亮度的寫法
  sensor_t * s = esp_camera_sensor_get();
  if (s) {
    s->set_vflip(s, 1);          // 解決上下相反
    s->set_hmirror(s, 1);        // 解決左右相反
    s->set_gain_ctrl(s, 1);      // 自動增益 (解決畫面變暗)
    s->set_exposure_ctrl(s, 1);  // 自動曝光
  }

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(500);
}

void loop() {
  camera_fb_t * fb = esp_camera_fb_get();
  if (fb) {
    HTTPClient http;
    http.begin(relayServer);
    http.addHeader("Content-Type", "image/jpeg");
    http.POST(fb->buf, fb->len);
    esp_camera_fb_return(fb);
    http.end();
  }
  delay(1000); // 每秒 1 幀
}