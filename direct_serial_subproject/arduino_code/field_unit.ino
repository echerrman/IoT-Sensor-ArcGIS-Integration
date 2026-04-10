/*
  RemoteUnit_DHT22_Tx.ino

  TRANSMITTER ARDUINO - Remote sensor unit (one per location)

  Reads temperature from DHT22 sensor and transmits via RS-485 to receiver.

  HARDWARE:
  - Arduino (any model)
  - DHT22 temperature/humidity sensor
  - RS-485 transceiver shield (uses hardware serial on pins 0/1)
  - Power supply (battery or wall)

  CONNECTIONS:
  - DHT22 data pin → Digital pin 2
  - RS-485 shield → Uses hardware serial pins 0/1 (built-in to shield)

  TO MODIFY FOR MULTIPLE SENSORS:
  1. Change the SENSOR_ID constant below to match your sensor
  2. The RS485.println() line will send "sensor_id:temperature" format

  Example:
  - SENSOR_ID = "sensor_1" sends: "sensor_1:72.34"
  - SENSOR_ID = "sensor_2" sends: "sensor_2:72.34"
  - etc.
*/

#include "DHT.h"

// ===== CHANGE THIS FOR DIFFERENT SENSORS =====
const String SENSOR_ID = "sensor_1"; // Change to "sensor_2", "sensor_3", etc.
// ============================================

// DHT22 sensor settings
#define DHTPIN 2
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

void setup()
{
    Serial.begin(9600); // Hardware serial to RS-485 shield (pins 0/1)
    dht.begin();        // Initialize DHT22 sensor
}

void loop()
{
    delay(2000); // Wait 2 seconds between readings

    // Read temperature from DHT22
    float tempF = dht.readTemperature(true);

    // Check if read was successful
    if (isnan(tempF))
    {
        Serial.println("ERROR: DHT sensor read failed");
        return;
    }

    // Send temperature with sensor ID over RS-485 to receiver
    // Format: "sensor_1:72.34"
    // This line transmits to BOTH RS485 shield (in field) AND Serial Monitor (when plugged in)
    Serial.print(SENSOR_ID);
    Serial.print(":");
    Serial.println(tempF, 2); // 2 decimal places
}
