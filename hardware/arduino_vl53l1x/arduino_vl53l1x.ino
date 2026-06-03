// Arduino Uno + VL53L1X
// Sends distance values to the Raspberry Pi over USB serial as:
// DISTANCE:523

#include <Wire.h>
#include <VL53L1X.h>

VL53L1X sensor;

void setup() {
  Serial.begin(115200);
  Wire.begin();

  if (!sensor.init()) {
    Serial.println("DISTANCE_ERROR");
    return;
  }

  sensor.setDistanceMode(VL53L1X::Long);
  sensor.setMeasurementTimingBudget(50000);
  sensor.startContinuous(100);
}

void loop() {
  if (sensor.timeoutOccurred()) {
    Serial.println("DISTANCE_ERROR");
    delay(100);
    return;
  }

  uint16_t distance = sensor.read();

  if (sensor.timeoutOccurred() || distance == 0) {
    Serial.println("DISTANCE_ERROR");
  } else {
    Serial.print("DISTANCE:");
    Serial.println(distance);
  }

  delay(100);
}
