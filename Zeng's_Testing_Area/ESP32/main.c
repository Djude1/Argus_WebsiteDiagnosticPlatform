// 初始化測試ESP32
const int ledPin = 2;

void setup() {
  // 初始化序列埠，鮑率設定為 115200
  Serial.begin(115200);
  
  // 設定 LED 接腳為輸出模式
  pinMode(ledPin, OUTPUT);
  
  Serial.println("--- ESP32 測試開始 ---");
}

void loop() {
  // 開燈
  digitalWrite(ledPin, HIGH);
  Serial.println("LED 狀態: 開 (ON)");
  delay(1000); // 等待 1 秒

  // 關燈
  digitalWrite(ledPin, LOW);
  Serial.println("LED 狀態: 關 (OFF)");
  delay(1000); // 等待 1 秒
}
