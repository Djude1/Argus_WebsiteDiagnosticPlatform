// File: firmware/main/main.ino

#include <WiFi.h>
#include "../camera.h"
#include "../gyroscope.h"
#include "../mic.h"

const char* ssid = "HelloWorld";
const char* password = "Aa0978926291";

void setup() {
  Serial.begin(115200);
  // Keep trying to connect or print debug
  Serial.setDebugOutput(true);
  Serial.println();

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.println("WiFi connected");

  // Init Peripherals
  initCamera();
  initGyro();
  initMic();

  // Start Server
  startCameraServer();

  Serial.print("Camera Ready! Use 'http://");
  Serial.print(WiFi.localIP());
  Serial.println("/stream' to connect");
}

void loop() {
  // Read Gyro data periodically for verification
  static unsigned long lastTime = 0;
  if (millis() - lastTime > 2000) {
    readGyro();
    lastTime = millis();
  }
  delay(10);
}
