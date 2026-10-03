// Arduino UNO R4 WiFi + Grove moisture v1.4 (A0), light v1.2 (A1), touch v1.1 (D2).
// Our protocol, not an assumed factory protocol. See docs/arduino-setup.md.
#include <Arduino.h>
#include <string.h>

constexpr int MOISTURE_PIN = A0;
constexpr int LIGHT_PIN = A1;
constexpr int TOUCH_PIN = 2;
constexpr unsigned long SAMPLE_MS = 1000;
constexpr unsigned long DEBOUNCE_MS = 40;
constexpr char DEVICE_ID[] = "arduino-plant-1";
char sessionId[37] = "";
char command[64];
size_t commandSize = 0;
unsigned long sequence = 0;
unsigned long lastSample = 0;
unsigned long changedAt = 0;
bool candidate = false;
bool pressed = false;

void emit(const char* type) {
  if (!sessionId[0]) return;
  Serial.print("{\"protocol\":\"talking-plant/1\",\"type\":\"");
  Serial.print(type);
  Serial.print("\",\"device_id\":\""); Serial.print(DEVICE_ID);
  Serial.print("\",\"session_id\":\""); Serial.print(sessionId);
  Serial.print("\",\"sequence\":"); Serial.print(sequence++);
  Serial.print(",\"uptime_ms\":"); Serial.print(millis());
  if (strcmp(type, "sensor") == 0) {
    Serial.print(",\"moisture_raw\":"); Serial.print(analogRead(MOISTURE_PIN));
    Serial.print(",\"light_raw\":"); Serial.print(analogRead(LIGHT_PIN));
  }
  Serial.print(",\"touch\":"); Serial.print(pressed ? "true" : "false");
  Serial.println("}");
}

void acceptCommand() {
  command[commandSize] = '\0';
  if (commandSize != 42 || strncmp(command, "START ", 6) != 0) return;
  // Only UUID characters; never reflect arbitrary serial text into JSON.
  for (size_t i = 6; i < 42; ++i) {
    char c = command[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || c == '-')) return;
  }
  if (strcmp(sessionId, command + 6) == 0) return;
  memcpy(sessionId, command + 6, 36); sessionId[36] = '\0';
  sequence = 0;
  pressed = candidate = digitalRead(TOUCH_PIN) == HIGH;
  changedAt = lastSample = millis();
  emit("sensor");
}

void setup() {
  pinMode(TOUCH_PIN, INPUT);
  analogReadResolution(10); // Explicit 0..1023 ADC scale on UNO R4.
  Serial.begin(115200);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { acceptCommand(); commandSize = 0; }
    else if (c != '\r') {
      if (commandSize < sizeof(command) - 1) command[commandSize++] = c;
      else commandSize = 0;
    }
  }
  const unsigned long now = millis();
  const bool reading = digitalRead(TOUCH_PIN) == HIGH;
  if (reading != candidate) { candidate = reading; changedAt = now; }
  if (candidate != pressed && now - changedAt >= DEBOUNCE_MS) {
    pressed = candidate;
    emit("touch");
  }
  if (now - lastSample >= SAMPLE_MS) {
    lastSample = now;
    emit("sensor"); // Includes touch heartbeat; a held pad is not a new pat.
  }
}
