from database import init_db
from mqtt_ingest import start

# ===============================
# RESET STALE EVACUATION STATE
# ===============================

import sqlite3
from datetime import datetime

import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "path_information.db")

def reset_stale_evacuation_state():
    """
    Clears old shelter/evacuation flags in the database so the application
    does not stay stuck in a SAFE or EVACUATION mode on startup.

    This function connects to the `path_information.db` and resets the 
    `is_evacuating`, `is_sheltering`, `current_step`, and `progress_percent` 
    fields for all tracking paths. It is typically called once on system boot.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("""
            UPDATE path_information
            SET
                is_evacuating = 0,
                is_sheltering = 0,
                current_step = 0,
                progress_percent = 0,
                last_updated = ?
        """, (datetime.now().isoformat(),))

        conn.commit()
        conn.close()

        print("[RESET] Evacuation state reset (0,0)")

    except Exception as e:
        print("[RESET] Failed:", e)




if __name__ == "__main__":
    init_db()
    print("[SYSTEM] XAI Safety System Running")
    reset_stale_evacuation_state()
    start()
