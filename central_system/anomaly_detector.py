import statistics
import subprocess
import sys
from config import *

# -------------------------------------------------
# GLOBAL FIRE STATE
# -------------------------------------------------
fire_system_process = None
active_fire_nodes = set()   # Tracks nodes currently reporting fire


def check_anomalies(node_id, history, data):
    """
    Analyzes recent sensor data to detect environmental anomalies and fire events.

    This function applies two types of checks:
    1. Absolute threshold checks (e.g., Temperature > 37°C).
    2. Relative spike detection (comparing current data to a rolling average history).

    It also handles a global fire state: if any node detects a fire, it will 
    spawn the standalone `safety_system.py` process to manage the emergency response.
    When all fires are cleared, it terminates the process.

    Args:
        node_id (str): The unique identifier for the apartment/node.
        history (dict): Dictionary containing lists of historical sensor values.
        data (dict): The current sensor reading to evaluate.

    Returns:
        list: A list of detected anomalies in the format (parameter, value, explanation).
    """
    global fire_system_process, active_fire_nodes

    anomalies = []

    # -------------------------------------------------
    # FIRE (GLOBAL, MULTI-NODE SAFE)
    # -------------------------------------------------
    if data["fire_state"] == FIRE_STATE_TRIGGER:
        #anomalies.append(("fire_state", 1, "Fire detected"))
        active_fire_nodes.add(node_id)
    else:
        active_fire_nodes.discard(node_id)

    # 🔥 Start fire system if ANY node has fire
    if active_fire_nodes:
        if fire_system_process is None or fire_system_process.poll() is not None:
            try:
                fire_system_process = subprocess.Popen(
                    [sys.executable, "safety_system.py"]
                )
                print(f"🔥 Fire system STARTED | Active fire nodes: {active_fire_nodes}")
            except Exception as e:
                print("❌ Failed to start fire safety system:", e)

    # 🟢 Stop fire system ONLY when ALL nodes are clear
    else:
        if fire_system_process is not None and fire_system_process.poll() is None:
            fire_system_process.terminate()
            fire_system_process = None
            print("🟢 All fires cleared → safety system STOPPED")

    # -------------------------------------------------
    # ABSOLUTE THRESHOLDS
    # -------------------------------------------------
    if data["temperature"] >= TEMP_MAX:
        anomalies.append(("temperature", data["temperature"],
                          "Temperature exceeded safe limit"))

    if data["humidity"] >= HUMIDITY_MAX:
        anomalies.append(("humidity", data["humidity"],
                          "Humidity exceeded safe limit"))

    if not (PRESSURE_MIN <= data["pressure"] <= PRESSURE_MAX):
        anomalies.append(("pressure", data["pressure"],
                          "Abnormal atmospheric pressure"))

    if data["gas_level"] >= GAS_MAX:
        anomalies.append(("gas_level", data["gas_level"],
                          "Gas concentration exceeded safe limit"))

    if data["sound_level"] >= SOUND_MAX:
        anomalies.append(("sound_level", data["sound_level"],
                          "Sound level exceeded safe limit"))

    # -------------------------------------------------
    # RELATIVE (SPIKE DETECTION)
    # -------------------------------------------------
    for key in ["temperature", "humidity", "pressure", "gas_level", "sound_level"]:
        if len(history[key]) >= MIN_HISTORY:
            avg = statistics.mean(history[key])
            if avg > 0 and data[key] > avg * RELATIVE_MULTIPLIER:
                anomalies.append((key, data[key],
                                  f"Sudden spike in {key}"))

    return anomalies
