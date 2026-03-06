// File: firmware/mic.h

#ifndef MIC_H
#define MIC_H

#include <driver/i2s.h>

// User provided: SCK=42, WS=41, SD=41.
// Part number: MSM261D3526H1CPM (PDM Microphone).
// Interpretation:
// PDM CLK = 42 (Mapped to I2S WS pin in PDM mode)
// PDM DATA = 41 (Mapped to I2S DIN pin)

#define I2S_MIC_CLK 42
#define I2S_MIC_DATA 41
#define I2S_PORT I2S_NUM_0

void initMic() {
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX | I2S_MODE_PDM),
    .sample_rate = 16000,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = 1024,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = -1
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_PIN_NO_CHANGE,
    .ws_io_num = I2S_MIC_CLK,      // PDM CLK
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_MIC_DATA    // PDM DATA
  };

  esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  if (err != ESP_OK) {
    Serial.printf("Failed installing I2S driver: %d\n", err);
    return;
  }

  err = i2s_set_pin(I2S_PORT, &pin_config);
  if (err != ESP_OK) {
    Serial.printf("Failed setting I2S pins: %d\n", err);
    return;
  }

  i2s_zero_dma_buffer(I2S_PORT);

  Serial.println("I2S Mic Initialized (PDM Mode)");
}

// Helper to read data if needed
int readMic(char* data, int len) {
    size_t bytes_read;
    i2s_read(I2S_PORT, (void*)data, len, &bytes_read, portMAX_DELAY);
    return bytes_read;
}

#endif
