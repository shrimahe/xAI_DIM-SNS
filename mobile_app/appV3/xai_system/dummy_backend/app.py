from flask import Flask, jsonify
from flask_cors import CORS
import time
from datetime import datetime

app = Flask(__name__)
CORS(app)

@app.route("/api/nodes/<node_id>")
def node_status(node_id):
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    iso_time = datetime.utcnow().isoformat()

    response = {
        "anomaly": {
            "explanation": f"The anomaly for {node_id} indicates a fire state with an elevation percentage of 100.0, posing a highly risky condition.",
            "parameter": "multiple",
            "timestamp": current_time,
            "value": 1.0
        },
        "fire_states": {
            "Apt1A": 0,
            "Apt1B": 0,
            "Apt2A": 0,
            "Apt2B": 0
        },
        "node_data": {
            "fire_state": 0,
            "gas_level": 43.0,
            "humidity": 42.3,
            "node_id": node_id,
            "pressure": 924.56,
            "sound_level": 74.0,
            "temperature": 29.25,
            "timestamp": current_time
        },
        "path_information": [
            {
                "assigned_exit": "EXIT_A",
                "current_step": 1,
                "direction_summary": "EAST -> NORTH -> EXIT_A",
                "file_name": "12345678-1234-1234-1234-1234567890ab.json",
                "is_evacuating": 1,
                "is_sheltering": 0,
                "last_updated": iso_time,
                "path_nodes": "[\"W_Mid\", \"CENTER\", \"E_Mid\", \"NE\"]",
                "position_x": 0.15,
                "position_y": 0.4199,
                "progress_percent": 25.0,
                "total_steps": 4,
                "turn_by_turn_instructions": "[\"1. Head EAST towards CENTER\", \"2. Continue EAST towards E_Mid\", \"3. Turn LEFT and go NORTH towards NE\", \"4. Exit through EXIT_A\"]"
            },
            {
                "assigned_exit": "EXIT_B",
                "current_step": 0,
                "direction_summary": "",
                "file_name": "11111111-2222-3333-4444-555555555555.json",
                "is_evacuating": 0,
                "is_sheltering": 0,
                "last_updated": iso_time,
                "path_nodes": "[]",
                "position_x": 0.3937,
                "position_y": 0.5119,
                "progress_percent": 100.0,
                "total_steps": 0,
                "turn_by_turn_instructions": "[]"
            },
            {
                "assigned_exit": "EXIT_A",
                "current_step": 0,
                "direction_summary": "",
                "file_name": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.json",
                "is_evacuating": 0,
                "is_sheltering": 0,
                "last_updated": iso_time,
                "path_nodes": "[]",
                "position_x": 0.3887,
                "position_y": 0.4169,
                "progress_percent": 100.0,
                "total_steps": 0,
                "turn_by_turn_instructions": "[]"
            }
        ],
        "safety_score": 36
    }

    return jsonify(response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
