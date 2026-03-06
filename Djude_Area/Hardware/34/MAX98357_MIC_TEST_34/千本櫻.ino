#include "driver/i2s.h"
#include <math.h>

// 1. 硬體腳位定義 (根據照片)
#define I2S_BCLK      7   // D8 / GPIO 7
#define I2S_LRCK      8   // D9 / GPIO 8
#define I2S_DIN       9   // D10 / GPIO 9
#define I2S_NUM       I2S_NUM_0

// 2. 音高頻率定義
#define A0 0
#define A3 556
#define A5 661
#define A6 742
#define AH1 882
#define AH2 990
#define AH3 1112
#define AH4 1178
#define AH5 1322
#define AH6 1484

// 3. 歌曲旋律與節奏
int tune[] = {
  A0,A0,A0,A3,A5,A6,A0,A0,A5,A6,A0,A0,A5,A6,AH1,A5,A6,A3,A0,A3,A5,
  A6,A0,A0,A5,A6,A0,A0,A5,A6,AH3,AH1,AH2,A6,A0,A3,A5,A6,A0,A0,A5,
  A6,A0,A0,A5,A6,AH1,A5,A6,A3,A5,556,556,A3,AH1,A6,AH3,AH2,AH3,AH2,
  AH1,AH2,A6,A0,A6,A6,A6,A6,AH1,AH2,AH3,A6,A6,A6,A5,A5,A6,A6,A6,A6,
  A6,AH1,AH2,AH3,A6,A6,A6,AH4,AH4,AH3,A6,A6,A6,A6,AH1,AH2,AH3,A6,A6,
  A6,A5,A5,A6,A6,A6,A6,A6,AH1,AH2,AH3,AH6,A5,A5,A6,A6
};

float duration[] = {
  1,1,1,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,
  0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,
  0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,1,1,1,1,0.5,0.25,0.25,0.5,
  0.5,1,1,1,1,1,0.25,0.25,0.25,0.25,1,1,0.5,0.5,0.5,0.5,1,1,1,0.25,0.25,
  0.25,0.25,1,1,0.5,0.5,0.5,0.5,1,1,1,0.25,0.25,0.25,0.25,1,1,0.5,0.5,0.5,0.5,
  1,1,1,0.25,0.25,0.25,0.25,1.5,0.5,0.5,0.5,1
};

int musicLength = sizeof(tune) / sizeof(tune[0]);

void setupI2S() {
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate = 44100,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT, 
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 128
  };
  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_BCLK,
    .ws_io_num = I2S_LRCK,
    .data_out_num = I2S_DIN,
    .data_in_num = I2S_PIN_NO_CHANGE
  };
  i2s_driver_install(I2S_NUM, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_NUM, &pin_config);
}

void playSilence(int len_ms) {
  size_t bytes_written;
  int samples = (44100 * len_ms) / 1000;
  int16_t silence[2] = {0, 0};
  for (int i = 0; i < samples; i++) {
    i2s_write(I2S_NUM, silence, sizeof(silence), &bytes_written, portMAX_DELAY);
  }
}

void playNote(int freq, int len_ms) {
  if (freq == 0) { 
    playSilence(len_ms); 
    return; 
  }
  
  size_t bytes_written;
  int samples = (44100 * len_ms) / 1000;
  int max_amplitude = 1600; // 再次微調音量以防止爆音

  for (int i = 0; i < samples; i++) {
    float envelope = 1.0;
    // 使用緩衝區刷新邏輯，確保每個音符轉折圓滑
    if (i < 400) envelope = i / 400.0; 
    if (i > samples - 400) envelope = (float)(samples - i) / 400.0;

    int16_t sample = (int16_t)(max_amplitude * envelope * sin(2 * M_PI * freq * i / 44100));
    int16_t buffer[2] = {sample, sample}; 
    i2s_write(I2S_NUM, buffer, sizeof(buffer), &bytes_written, portMAX_DELAY);
  }
  playSilence(5); 
}

void setup() {
  Serial.begin(115200);
  setupI2S();
  Serial.println("🎵 播放終極修復版...");
}

void loop() {
  for (int i = 0; i < musicLength; i++) {
    playNote(tune[i], 450 * duration[i]);
  }
  
  // 歌曲結束後強制靜音 100 毫秒，清空緩衝區
  playSilence(100);
  delay(3000); 
}