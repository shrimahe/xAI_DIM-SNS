# IoT Sensor Node (ESP32)

This directory contains the C++ firmware (`main.cpp`) for the IoT Edge Nodes used in the **xAI Apartment Safety System**. The code is designed to run on an **ESP32 Microcontroller**.

## Overview

The sensor node is responsible for two primary parallel tasks utilizing the ESP32's dual-core architecture (FreeRTOS):

1. **Environmental Monitoring (Core 0)**: Reads temperature, humidity, and atmospheric pressure. It also performs Fast Fourier Transform (FFT) on analog audio/gas sensors to extract peak magnitudes for noise and gas levels. A physical push-button acts as a manual fire alarm override.
2. **Indoor Positioning System (IPS) via BLE (Core 1)**: Continuously scans for specific BLE MAC addresses or UUIDs representing resident wearables. It applies a 1D Kalman Filter to smooth the RSSI signals and estimates the distance between the node and the user.

All collected data is packaged into JSON payloads and published to the central Mosquitto MQTT broker.

## Hardware Requirements

- **Microcontroller**: ESP32 Development Board
- **Sensors**:
  - **BME280**: Temperature, Humidity, and Pressure (I2C)
  - **MQ2**: Gas Sensor (Analog)
  - **Microphone**: Sound Level (Analog)
  - **Push Button**: Manual Fire Trigger
- **Indicators**: Red and Green LEDs

## Wiring Guide (Default Configuration)

| Component    | ESP32 Pin | Note |
|--------------|-----------|------|
| BME280 SDA   | GPIO 21   | I2C Data |
| BME280 SCL   | GPIO 22   | I2C Clock |
| MQ2 Analog   | GPIO 34   | Analog input for gas concentration |
| Mic Analog   | GPIO 35   | Analog input for noise level |
| Push Button  | GPIO 15   | Uses internal pull-down; triggers on HIGH |
| Red LED      | GPIO 4    | Fire Indicator |
| Green LED    | GPIO 0    | Normal Operation Indicator |

## Software Dependencies

Ensure the following libraries are installed in your Arduino IDE or PlatformIO environment:

- `WiFi.h` (Built-in)
- `PubSubClient` (for MQTT communication)
- `BLEDevice`, `BLEScan` (Built-in ESP32 BLE libraries)
- `Wire` (Built-in)
- `Adafruit Unified Sensor`
- `Adafruit BME280 Library`
- `arduinoFFT` (for processing analog signals)

## Configuration

Before flashing the code to your ESP32, update the macros at the top of `main.cpp` to match your environment:

```cpp
/* ================= NODE CONFIG ================= */
#define NODE_ID "Apt2B" // Identifier for this specific node

/* ================= WIFI + MQTT ================= */
const char* WIFI_SSID   = "Your_WiFi_SSID";
const char* WIFI_PASS   = "Your_WiFi_Password";
const char* MQTT_BROKER = "192.168.x.x"; // IP of your central server
const int   MQTT_PORT   = 1883;

/* ================= TRACKING CONFIG ================= */
// Add the specific BLE UUIDs of the wearables you want to track
const char* TRACK_UUIDS[MAX_PERSONS] = {
  "12345678-1234-1234-1234-1234567890ab",
  // ...
};
```

## Indoor Positioning System (IPS) Mechanism

The sensor nodes act as beacons for an Indoor Positioning System (IPS) to locate residents during an emergency. The mechanism works as follows:

1. **BLE Scanning**: The ESP32 utilizes a dedicated FreeRTOS task on Core 1 to continuously scan for Bluetooth Low Energy (BLE) advertisements. It looks specifically for devices broadcasting UUIDs listed in the `TRACK_UUIDS` array (representing resident wearables or mobile apps).
2. **RSSI Smoothing (Kalman Filter)**: Raw Bluetooth signal strength (RSSI) is inherently noisy and fluctuates rapidly. The node applies a 1-Dimensional Kalman Filter to the incoming RSSI values for each tracked person. This drastically reduces noise and provides a stable signal strength estimate.
3. **Distance Calculation**: The smoothed RSSI is converted into an estimated physical distance (in meters) using the Log-Normal Shadowing Model equation:
   `Distance = 10 ^ ((TX_Power - RSSI) / (10 * Path_Loss))`
   *(The `TX_POWER` and `PATH_LOSS` constants can be calibrated at the top of the file).*
4. **Telemetry**: The node publishes the calculated distance and presence state to the central server via MQTT, which then aggregates distances from multiple nodes to triangulate the exact position of the person.

## How It Works

1. **Setup**: The ESP32 connects to the specified Wi-Fi network and MQTT broker. It initializes the BME280 sensor, sets up GPIO pins for the LEDs and the button interrupt, and configures the BLE scanner.
2. **BLE Task**: Runs independently. If it detects a predefined UUID, it calculates the distance using the Kalman-filtered RSSI and publishes a tracking JSON to `building/<NODE_ID>/<UUID>`.
3. **Sensor Task**: Reads the environmental sensors. It uses FFT over 128 samples at 4000Hz to calculate peak decibel magnitudes for the microphone and gas sensor. It publishes a sensor JSON payload to `building/<NODE_ID>/sensors` every 10 seconds.
4. **Fire Override**: Pressing the physical button triggers a hardware interrupt that toggles the `fire_state` flag globally across the system, immediately alerting the central analytics engine.
