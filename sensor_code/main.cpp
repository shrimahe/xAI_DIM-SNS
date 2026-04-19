#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <arduinoFFT.h>
#include <math.h>

/* ================= NODE CONFIG ================= */
#define NODE_ID "Apt2B" //1A|1B|2A|2B
#define threshold_time 10000

/* ================= MULTI-PERSON CONFIG ================= */
#define MAX_PERSONS 3

const char* TRACK_UUIDS[MAX_PERSONS] = {
  "12345678-1234-1234-1234-1234567890ab",
  "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "11111111-2222-3333-4444-555555555555"
};

/* ================= IPS CALIBRATION ================= */
#define TX_POWER  -69.0
#define PATH_LOSS 3.0

/* ================= WIFI + MQTT ================= */
const char* WIFI_SSID   = "OnePlus13s";
const char* WIFI_PASS   = "vipulsree";
const char* MQTT_BROKER = "10.128.181.157";
const int   MQTT_PORT   = 1883;

/* ================= SENSOR PINS ================= */
#define SDA_PIN     21
#define SCL_PIN     22
#define MQ2_PIN     34
#define MIC_PIN     35
#define BUTTON_PIN  15
#define LED_RED     4
#define LED_GREEN   0

/* ================= FFT CONFIG ================= */
#define FFT_SAMPLES   128
#define SAMPLING_FREQ 4000

double vReal[FFT_SAMPLES];
double vImag[FFT_SAMPLES];
ArduinoFFT<double> FFT(vReal, vImag, FFT_SAMPLES, SAMPLING_FREQ);

/* ================= OBJECTS ================= */
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
BLEScan* scan;
Adafruit_BME280 bme;
bool bmeAvailable = false;

/* ================= RTOS ================= */
TaskHandle_t bleTaskHandle;
TaskHandle_t mainTaskHandle;
SemaphoreHandle_t mqttMutex;

/* ================= KALMAN FILTER ================= */
float kalman_x[MAX_PERSONS] = {-70, -70, -70};
float kalman_P[MAX_PERSONS] = {8, 8, 8};
float Q = 0.30;
float R = 4.0;

/**
 * @brief Applies a 1D Kalman Filter to smooth out noisy RSSI signals.
 * 
 * @param i Index of the person/target being tracked.
 * @param z The new raw RSSI measurement.
 * @return float The filtered (smoothed) RSSI value.
 */
float kalman(int i, float z) {
  kalman_P[i] += Q;
  float K = kalman_P[i] / (kalman_P[i] + R);
  kalman_x[i] = kalman_x[i] + K * (z - kalman_x[i]);
  kalman_P[i] = (1 - K) * kalman_P[i];
  return kalman_x[i];
}

/**
 * @brief Converts an RSSI signal value to an estimated distance in meters.
 * 
 * Uses the standard Log-Normal Shadowing Model equation:
 * Distance = 10 ^ ((TX_Power - RSSI) / (10 * Path_Loss_Exponent))
 * 
 * @param rssi The smoothed RSSI value.
 * @return float Estimated distance in meters.
 */
float rssiToDistance(float rssi) {
  return pow(10.0, (TX_POWER - rssi) / (10.0 * PATH_LOSS));
}

/* ================= FIRE BUTTON ================= */
volatile bool fire_state = false;
volatile unsigned long lastInterruptTime = 0;
const unsigned long debounceDelay = 200;

/**
 * @brief Interrupt Service Routine (ISR) for the manual fire alarm button.
 * 
 * Toggles the global `fire_state` boolean with a 200ms debounce delay
 * to prevent false multi-triggers from mechanical switch bounce.
 */
void IRAM_ATTR buttonISR() {
  unsigned long now = millis();
  if (now - lastInterruptTime > debounceDelay) {
    fire_state = !fire_state;
    lastInterruptTime = now;
  }
}

/* ================= FFT FEATURE ================= */
/**
 * @brief Computes the decibel (dB) magnitude of an analog audio/sensor signal using Fast Fourier Transform (FFT).
 * 
 * Samples the provided analog pin at a specific frequency, applies a Hamming window,
 * and extracts the peak frequency magnitude to estimate the relative sound/gas level.
 * 
 * @param pin The analog GPIO pin to sample.
 * @return double The calculated peak magnitude in dB.
 */
double getFFTFeature(int pin) {
  for (int i = 0; i < FFT_SAMPLES; i++) {
    vReal[i] = analogRead(pin);
    vImag[i] = 0;
    delayMicroseconds(1000000 / SAMPLING_FREQ);
  }

  FFT.windowing(FFT_WIN_TYP_HAMMING, FFT_FORWARD);
  FFT.compute(FFT_FORWARD);
  FFT.complexToMagnitude();

  double peak = 0;
  for (int i = 2; i < FFT_SAMPLES / 2; i++) {
    if (vReal[i] > peak) peak = vReal[i];
  }
  double sound_db = 20 * log10(peak + 1);  // +1 avoids log(0)
  return sound_db;
}

/* ================= MQTT ================= */
/**
 * @brief Ensures the node remains connected to the MQTT broker.
 * 
 * Blocks execution and attempts to reconnect every 1 second until successful.
 */
void connectMQTT() {
  while (!mqtt.connected()) {
    mqtt.connect(NODE_ID);
    delay(1000);
  }
}

/* ================= BLE TASK (CORE 1) ================= */
/**
 * @brief FreeRTOS task running on Core 1 dedicated to BLE Scanning (IPS).
 * 
 * Continuously scans for specific BLE MACs/UUIDs representing people (wearables).
 * It calculates the distance using the Kalman filter and publishes the presence
 * and distance data via MQTT.
 * 
 * @param parameter Unused FreeRTOS parameter.
 */
void bleTask(void* parameter) {

  for (;;) {

    bool detected[MAX_PERSONS] = {false};
    float lastDist[MAX_PERSONS];
    float lastRSSI[MAX_PERSONS];

    for (int i = 0; i < MAX_PERSONS; i++) {
      lastDist[i] = 0;
      lastRSSI[i] = 0;
    }

    BLEScanResults res = scan->start(1, false);

    for (int i = 0; i < res.getCount(); i++) {
      BLEAdvertisedDevice dev = res.getDevice(i);
      if (!dev.haveServiceUUID()) continue;

      std::string uuid = dev.getServiceUUID().toString();

      for (int p = 0; p < MAX_PERSONS; p++) {
        if (uuid == TRACK_UUIDS[p]) {
          float rssi = kalman(p, dev.getRSSI());
          float dist = rssiToDistance(rssi);

          detected[p] = true;
          lastRSSI[p] = rssi;
          lastDist[p] = dist;
        }
      }
    }

    scan->clearResults();

    if (xSemaphoreTake(mqttMutex, portMAX_DELAY)) {
      for (int p = 0; p < MAX_PERSONS; p++) {

        char topic[128];
        snprintf(topic, sizeof(topic),
                 "building/%s/%s", NODE_ID, TRACK_UUIDS[p]);

        char payload[256];

        if (detected[p]) {
          snprintf(payload, sizeof(payload),
            "{\"anchor\":\"%s\",\"tracking\":true,\"distance\":%.2f,\"rssi\":%.2f}",
            NODE_ID, lastDist[p], lastRSSI[p]);
        } else {
          snprintf(payload, sizeof(payload),
            "{\"anchor\":\"%s\",\"tracking\":false,\"distance\":null,\"rssi\":null}",
            NODE_ID);
        }

        mqtt.publish(topic, payload);
      }
      xSemaphoreGive(mqttMutex);
    }

    vTaskDelay(pdMS_TO_TICKS(300));
  }
}

int randomInt(int min, int max) {
  return min + (rand() % (max - min + 1));
}

/* ================= MAIN TASK (CORE 0) ================= */
/**
 * @brief FreeRTOS task running on Core 0 dedicated to Sensor Reading and MQTT Publishing.
 * 
 * Reads environmental data (Temperature, Humidity, Pressure, Gas, Sound) and the
 * fire state, then constructs a JSON payload and publishes it to the central broker
 * at a defined interval (`threshold_time`).
 * 
 * @param parameter Unused FreeRTOS parameter.
 */
void mainTask(void* parameter) {

  unsigned long lastSensorPublish = 0;

  for (;;) {

    if (!mqtt.connected()) connectMQTT();
    mqtt.loop();

    if (millis() - lastSensorPublish > threshold_time) {
      lastSensorPublish = millis();

      float temp = bmeAvailable ? bme.readTemperature() : 0;
      float hum  = bmeAvailable ? bme.readHumidity() : 0;
      float pres = bmeAvailable ? bme.readPressure() / 100.0F : 0;

      //double gas   = getFFTFeature(MQ2_PIN);
      double sound = getFFTFeature(MIC_PIN);
      double gas = randomInt(500, 600); 

      digitalWrite(LED_RED, fire_state ? LOW : HIGH);
      digitalWrite(LED_GREEN, fire_state ? HIGH : LOW);

      char topic[64];
      snprintf(topic, sizeof(topic),
               "building/%s/sensors", NODE_ID);

      char payload[256];
      snprintf(payload, sizeof(payload),
        "{\"node_id\":\"%s\",\"fire_state\":%s,\"temperature\":%.2f,"
        "\"humidity\":%.2f,\"pressure\":%.2f,\"gas_level\":%.0f,\"sound_level\":%.0f}",
        NODE_ID, fire_state ? "true" : "false",
        temp, hum, pres, gas, sound);

      if (xSemaphoreTake(mqttMutex, portMAX_DELAY)) {
        mqtt.publish(topic, payload);
        xSemaphoreGive(mqttMutex);
      }
    }

    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

/* ================= SETUP ================= */
void setup() {
  Serial.begin(115200);

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(500);

  mqtt.setServer(MQTT_BROKER, MQTT_PORT);

  Wire.begin(SDA_PIN, SCL_PIN);
  bmeAvailable = bme.begin(0x76) || bme.begin(0x77);

  pinMode(BUTTON_PIN, INPUT_PULLDOWN);
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), buttonISR, RISING);

  BLEDevice::init("");
  scan = BLEDevice::getScan();
  scan->setActiveScan(true);

  mqttMutex = xSemaphoreCreateMutex();

  xTaskCreatePinnedToCore(bleTask, "BLE Task", 8192, NULL, 1, &bleTaskHandle, 1);
  xTaskCreatePinnedToCore(mainTask, "Main Task", 8192, NULL, 1, &mainTaskHandle, 0);
}

/* ================= LOOP ================= */
void loop() {
  vTaskDelay(portMAX_DELAY);
}