/*
  LocalUnit_AnalogRx.ino
  
  RECEIVER ARDUINO - Connects to computer via USB (COM7)
  
  Receives data from remote sensor Arduinos via RS-485 wireless transceivers
  and forwards everything to the computer's Serial Monitor (USB).
  
  This Arduino doesn't process data - just relays it.
  All sensor ID parsing happens in the Python code.
  
  HARDWARE:
  - Arduino Uno R3
  - RS-485 transceiver shield
  - USB cable to computer
  
  CONNECTIONS:
  - Pin 2 (RX) ↔ RO on RS-485 shield (receive)
  - Pin 3 (TX) ↔ DI on RS-485 shield (transmit)
  
  NOTE: This code doesn't need modification when adding sensors.
  Just program the remote sensor Arduinos with unique sensor IDs.
*/

#include <SoftwareSerial.h>

#define TX 3   // ↔ DI on shield
#define RX 2   // ↔ RO on shield

SoftwareSerial RS485(RX, TX);

void setup() {
  Serial.begin(9600);   // USB connection to computer
  RS485.begin(9600);    // Must match remote sensor baud rate
}

void loop() {
  // Forward any data from RS-485 to computer
  while (RS485.available()) {
    Serial.write(RS485.read());   // Echo byte-for-byte
  }
}
