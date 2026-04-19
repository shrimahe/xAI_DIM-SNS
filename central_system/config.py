import os

# ---------- Paths ----------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "data", "safety_xai.db")

# ---------- MQTT ----------
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_SENSOR_TOPIC = "building/+/sensors"
MQTT_XAI_TOPIC = "building/xai"

# ---------- ABSOLUTE SAFETY THRESHOLDS ----------
TEMP_MAX = 37.0            # °C
HUMIDITY_MAX = 85.0        # %
PRESSURE_MIN = 900.0       # hPa
PRESSURE_MAX = 1100.0      # hPa
GAS_MAX = 650             # ppm
SOUND_MAX = 85          # units
FIRE_STATE_TRIGGER = True

# ---------- RELATIVE (HISTORY-BASED) ----------
MIN_HISTORY = 5
RELATIVE_MULTIPLIER = 2.0
