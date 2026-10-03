const int MOISTURE_PIN = A0;
const int LIGHT_PIN = A1;
const int TOUCH_PIN = 2;
const int LED_PIN = 4;

unsigned long lastReport = 0;
int lastTouch = -1;
String inbound;

int readAveraged(int pin) {
  long sum = 0;
  for (int i = 0; i < 8; i++) { sum += analogRead(pin); delay(2); }
  return sum / 8;
}

void report(int touch) {
  Serial.print("{\"moisture_raw\":");
  Serial.print(readAveraged(MOISTURE_PIN));
  Serial.print(",\"light_raw\":");
  Serial.print(readAveraged(LIGHT_PIN));
  Serial.print(",\"touch\":");
  Serial.print(touch);
  Serial.println("}");
}

void setup() {
  Serial.begin(115200);
  pinMode(TOUCH_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);
}

void loop() {
  int touch = digitalRead(TOUCH_PIN) == HIGH ? 1 : 0;
  unsigned long now = millis();
  if (touch != lastTouch || now - lastReport >= 1000) {
    report(touch);
    lastTouch = touch;
    lastReport = now;
  }
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      bool unhappy = inbound.indexOf("thirsty") >= 0 || inbound.indexOf("dark") >= 0 || inbound.indexOf("unwell") >= 0;
      digitalWrite(LED_PIN, unhappy ? HIGH : LOW);
      inbound = "";
    } else if (c != '\r' && inbound.length() < 200) {
      inbound += c;
    }
  }
}
