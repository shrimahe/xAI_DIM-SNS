from flask import Flask, jsonify
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
CORS(app)

# -------------------------------------------------
# DATABASE CONFIG
# -------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SAFETY_DB = os.path.join(BASE_DIR, "safety_xai.db")
PATH_DB = os.path.join(BASE_DIR, "path_information.db")

# -------------------------------------------------
# NODE MAPPING
# -------------------------------------------------
NODE_MAP = {
    "1A": "Apt1A",
    "1B": "Apt1B",
    "2A": "Apt2A",
    "2B": "Apt2B",
}

ALL_NODES = ["Apt1A", "Apt1B", "Apt2A", "Apt2B"]

# -------------------------------------------------
# DB CONNECTIONS
# -------------------------------------------------
def get_safety_db():
    conn = sqlite3.connect(SAFETY_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_path_db():
    conn = sqlite3.connect(PATH_DB)
    conn.row_factory = sqlite3.Row
    return conn

# -------------------------------------------------
# FETCH FIRE STATE OF ALL NODES
# -------------------------------------------------
def get_all_fire_states(conn):
    fire_states = {}

    for node in ALL_NODES:
        row = conn.execute("""
            SELECT fire_state
            FROM sensor_readings
            WHERE node_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (node,)).fetchone()

        fire_states[node] = int(row["fire_state"]) if row else 0

    return fire_states

# -------------------------------------------------
# FETCH CURRENT ANOMALY
# -------------------------------------------------
def get_latest_anomaly(conn, node_id):
    row = conn.execute("""
        SELECT timestamp, parameter, value, explanation
        FROM anomalies
        WHERE node_id = ?
    """, (node_id,)).fetchone()

    return dict(row) if row else None

# -------------------------------------------------
# FETCH SAFETY SCORE
# -------------------------------------------------
def get_safety_score(conn, node_id):
    row = conn.execute("""
        SELECT score
        FROM apartment_scores
        WHERE apartment_id = ?
    """, (node_id,)).fetchone()

    return row["score"] if row else None

# -------------------------------------------------
# FETCH PATH INFORMATION
# -------------------------------------------------
def get_path_information():
    conn = get_path_db()
    rows = conn.execute("""
        SELECT
            file_name,
            position_x,
            position_y,
            is_evacuating,
            is_sheltering,
            assigned_exit,
            path_nodes,
            current_step,
            total_steps,
            progress_percent,
            direction_summary,
            turn_by_turn_instructions,
            last_updated
        FROM path_information
    """).fetchall()
    conn.close()

    return [dict(r) for r in rows]

# -------------------------------------------------
# GET LATEST DATA FOR ONE NODE
# -------------------------------------------------
@app.route("/api/nodes/<node>", methods=["GET"])
def get_node_latest(node):
    node = node.upper()

    if node not in NODE_MAP:
        return jsonify({"error": "Invalid node"}), 404

    mapped_node = NODE_MAP[node]
    safety_conn = get_safety_db()

    sensor_row = safety_conn.execute("""
        SELECT node_id, timestamp, fire_state,
               temperature, humidity, pressure,
               gas_level, sound_level
        FROM sensor_readings
        WHERE node_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (mapped_node,)).fetchone()

    if sensor_row is None:
        safety_conn.close()
        return jsonify({"error": "No data"}), 404

    response = {
        "node_data": dict(sensor_row),
        "anomaly": get_latest_anomaly(safety_conn, mapped_node),
        "safety_score": get_safety_score(safety_conn, mapped_node),
        "fire_states": get_all_fire_states(safety_conn),
        "path_information": get_path_information()
    }

    safety_conn.close()
    return jsonify(response)

# -------------------------------------------------
# GET DASHBOARD DATA (ALL NODES)
# -------------------------------------------------
@app.route("/api/nodes/latest", methods=["GET"])
def get_all_latest():
    safety_conn = get_safety_db()

    sensor_rows = safety_conn.execute("""
        SELECT s.*
        FROM sensor_readings s
        INNER JOIN (
            SELECT node_id, MAX(timestamp) AS max_time
            FROM sensor_readings
            GROUP BY node_id
        ) t
        ON s.node_id = t.node_id AND s.timestamp = t.max_time
    """).fetchall()

    fire_states = get_all_fire_states(safety_conn)
    path_info = get_path_information()

    result = []

    for row in sensor_rows:
        result.append({
            "node_data": dict(row),
            "anomaly": get_latest_anomaly(safety_conn, row["node_id"]),
            "safety_score": get_safety_score(safety_conn, row["node_id"]),
            "fire_states": fire_states,
            "path_information": path_info
        })

    safety_conn.close()
    return jsonify(result)

# -------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
