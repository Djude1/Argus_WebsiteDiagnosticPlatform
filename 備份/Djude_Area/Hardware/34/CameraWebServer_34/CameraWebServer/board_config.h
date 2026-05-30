#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

// ===================
// Select camera model
// ===================
// 將原本的 ESP_EYE 註解掉，並開啟 XIAO_ESP32S3
//#define CAMERA_MODEL_ESP_EYE 
#define CAMERA_MODEL_XIAO_ESP32S3 // 確保這一行是開啟的 (沒有 //)

#include "camera_pins.h"

#endif  // BOARD_CONFIG_H