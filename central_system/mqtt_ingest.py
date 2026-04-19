import json
import paho.mqtt.client as mqtt
from database import get_db
from anomaly_detector import check_anomalies
from xai_llama import explain
from config import *

history = {}

mqtt_pub = mqtt.Client()
mqtt_pub.connect(MQTT_BROKER, MQTT_PORT)


def elevation_percentage(current, threshold):
    if threshold <= 0:
        return 0.0
    return round(((current - threshold) / threshold) * 100, 1)


def on_message(client, userdata, msg):
    node_id = msg.topic.split("/")[1]
    data = json.loads(msg.payload.decode())

    history.setdefault(node_id, {
        "temperature": [],
        "humidity": [],
        "pressure": [],
        "gas_level": [],
        "sound_level": []
    })

    db = get_db()
    c = db.cursor()

    # -------------------------------------------------
    # STORE RAW SENSOR DATA
    # -------------------------------------------------
    c.execute("""
        INSERT INTO sensor_readings
        (node_id, fire_state, temperature, humidity, pressure, gas_level, sound_level)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        node_id,
        int(data["fire_state"]),
        data["temperature"],
        data["humidity"],
        data["pressure"],
        data["gas_level"],
        data["sound_level"]
    ))
    db.commit()

    # -------------------------------------------------
    # DETECT ANOMALIES (FIXED: pass node_id)
    # -------------------------------------------------
    anomalies = check_anomalies(node_id, history[node_id], data)

    if anomalies:
        anomaly_summary = []

        for param, value, _ in anomalies:
            if param == "temperature":
                elev = elevation_percentage(value, TEMP_MAX)
                limit = TEMP_MAX
            elif param == "humidity":
                elev = elevation_percentage(value, HUMIDITY_MAX)
                limit = HUMIDITY_MAX
            elif param == "pressure":
                elev = elevation_percentage(
                    abs(value - ((PRESSURE_MIN + PRESSURE_MAX) / 2)),
                    ((PRESSURE_MAX - PRESSURE_MIN) / 2)
                )
                limit = "normal range"
            elif param == "gas_level":
                elev = elevation_percentage(value, GAS_MAX)
                limit = GAS_MAX
            elif param == "sound_level":
                elev = elevation_percentage(value, SOUND_MAX)
                limit = SOUND_MAX
            elif param == "fire_state":
                elev = 100.0
                limit = "fire detected"
            else:
                elev = 0.0
                limit = "unknown"

            anomaly_summary.append({
                "parameter": param,
                "current_value": value,
                "safe_limit": limit,
                "elevation_percentage": elev
            })

        # -------------------------------------------------
        # XAI EXPLANATION
        # -------------------------------------------------
        context = {
            "apartment": node_id,
            "anomalies": anomaly_summary
        }

        explanation = explain(context)

        # -------------------------------------------------
        # UPSERT INTO anomalies TABLE
        # -------------------------------------------------
        c.execute("""
            INSERT INTO anomalies
            (node_id, timestamp, parameter, value, explanation)
            VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?)
            ON CONFLICT(node_id)
            DO UPDATE SET
                timestamp = excluded.timestamp,
                parameter = excluded.parameter,
                value = excluded.value,
                explanation = excluded.explanation
        """, (
            node_id,
            "multiple",
            len(anomaly_summary),
            explanation
        ))

        db.commit()

        # -------------------------------------------------
        # PUBLISH XAI RESULT
        # -------------------------------------------------
        mqtt_pub.publish(MQTT_XAI_TOPIC, json.dumps({
            "apartment": node_id,
            "anomalies": anomaly_summary,
            "xai_explanation": explanation
        }))

    # -------------------------------------------------
    # UPDATE HISTORY
    # -------------------------------------------------
    for key in history[node_id]:
        history[node_id][key].append(data[key])

    db.close()


def start():
    client = mqtt.Client()
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT)
    client.subscribe(MQTT_SENSOR_TOPIC)
    client.loop_forever()
