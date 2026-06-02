#include <Wire.h>
#include <VL53L1X.h>

VL53L1X sensor;

void setup() {
  Serial.begin(9600);
  Wire.begin();

  Serial.println("Initialisation VL53L1X...");

  sensor.setTimeout(500);

  if (!sensor.init()) {
    Serial.println("Erreur : VL53L1X non detecte !");
    while (1);
  }

  // Distance longue portee.
  sensor.setDistanceMode(VL53L1X::Long);

  // Temps de mesure en ms.
  sensor.setMeasurementTimingBudget(50000);

  // Demarrer la mesure continue chaque 50 ms.
  sensor.startContinuous(50);

  Serial.println("VL53L1X pret !");
}

void loop() {
  int distance = sensor.read();

  if (sensor.timeoutOccurred()) {
    Serial.println("Timeout !");
  } else {
    Serial.print("Distance: ");
    Serial.print(distance);
    Serial.println(" mm");
  }

  delay(100);
}
