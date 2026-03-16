/**
 * ============================================
 * XIAO ESP32-S3 Sense 攝影機 GPIO 定義
 * ============================================
 * 攝影機模組：TY-OV3660-75MM-V2.0
 * 感光元件：OV3660 (3MP)
 */

#ifndef CAMERA_PINS_H
#define CAMERA_PINS_H

// ============================================
// OV3660 攝影機 GPIO 定義 (XIAO ESP32-S3 Sense)
// ============================================

// 系統時鐘
#define XCLK_GPIO_NUM       10

// 像素時鐘
#define PCLK_GPIO_NUM       13

// 影格同步
#define VSYNC_GPIO_NUM      38

// 行同步
#define HREF_GPIO_NUM       47

// I2C 通訊 (攝影機控制)
#define SIOD_GPIO_NUM       40  // I2C SDA
#define SIOC_GPIO_NUM       39  // I2C SCL

// 影像資料線 (D0 ~ D7)
#define Y2_GPIO_NUM         15
#define Y3_GPIO_NUM         17
#define Y4_GPIO_NUM         18
#define Y5_GPIO_NUM         16
#define Y6_GPIO_NUM         14
#define Y7_GPIO_NUM         12
#define Y8_GPIO_NUM         11
#define Y9_GPIO_NUM         48

// 電源控制 (通常不使用)
#define PWDN_GPIO_NUM       -1
#define RESET_GPIO_NUM      -1

// ============================================
// 攝影機設定建議
// ============================================
/*
 * 解析度設定 (根據需求選擇)：
 * - FRAMESIZE_QVGA    : 320x240   (最快，適合測試)
 * - FRAMESIZE_VGA     : 640x480   (平衡選擇)
 * - FRAMESIZE_SVGA    : 800x600   (推薦)
 * - FRAMESIZE_XGA     : 1024x768  (高品質)
 * - FRAMESIZE_SXGA    : 1280x1024 (需要更多 PSRAM)
 * 
 * JPEG 品質 (0-63，數字越小品質越高)：
 * - 推薦值：12-15 (平衡品質與大小)
 * 
 * XCLK 頻率：
 * - 20MHz : 標準設定
 * - 10MHz : 降低延遲
 * - 2MHz  : 最低延遲 (可能影響畫質)
 */

#endif // CAMERA_PINS_H
