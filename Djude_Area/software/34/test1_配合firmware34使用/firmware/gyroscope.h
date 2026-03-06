// File: firmware/gyroscope.h

#ifndef GYROSCOPE_H
#define GYROSCOPE_H

#include <Wire.h>

#define ICM42688P_ADDR 0x68
#define PWR_MGMT0_REG  0x4E
#define ACCEL_DATA_X1  0x1F

void initGyro() {
  Wire.begin(4, 5); // SDA, SCL
  delay(10);

  // Wake up ICM42688P
  // Set Accel to Low Noise (LN) mode and Gyro to Low Noise (LN) mode
  // PWR_MGMT0: bits 3:2 = GYRO_MODE (11=LN), bits 1:0 = ACCEL_MODE (11=LN)
  // Register 0x4E.
  // Actually check datasheet:
  // Bit 3:2 GYRO_MODE: 00=OFF, 01=OFF, 10=STANDBY, 11=LN
  // Bit 1:0 ACCEL_MODE: 00=OFF, 01=OFF, 10=LP, 11=LN
  // So we want 0x0F (binary 0000 1111) to turn both on.

  Wire.beginTransmission(ICM42688P_ADDR);
  Wire.write(PWR_MGMT0_REG);
  Wire.write(0x0F);
  Wire.endTransmission();

  Serial.println("IMU Initialized (ICM42688P)");
}

void readGyro() {
  Wire.beginTransmission(ICM42688P_ADDR);
  Wire.write(ACCEL_DATA_X1);
  Wire.endTransmission(false);

  // Read 12 bytes: Accel X/Y/Z (2 bytes each) + Gyro X/Y/Z (2 bytes each)
  int bytesToRead = 12;
  Wire.requestFrom(ICM42688P_ADDR, bytesToRead);

  if (Wire.available() == bytesToRead) {
    int16_t accelX = (Wire.read() << 8) | Wire.read();
    int16_t accelY = (Wire.read() << 8) | Wire.read();
    int16_t accelZ = (Wire.read() << 8) | Wire.read();
    int16_t gyroX = (Wire.read() << 8) | Wire.read();
    int16_t gyroY = (Wire.read() << 8) | Wire.read();
    int16_t gyroZ = (Wire.read() << 8) | Wire.read();

    // Print to Serial for verification
    Serial.printf("IMU: A[%d, %d, %d] G[%d, %d, %d]\n", accelX, accelY, accelZ, gyroX, gyroY, gyroZ);
  } else {
    // Serial.println("IMU Read Error");
  }
}

#endif
