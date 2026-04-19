import sqlite3
from config import DB_FILE

def get_db():
    return sqlite3.connect(DB_FILE)

def init_db():
    print("[DB] Initializing database at:", DB_FILE)
    db = get_db()
    c = db.cursor()

    # ---- Raw sensor data (ALL parameters) ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS sensor_readings (
        node_id TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        fire_state INTEGER,
        temperature REAL,
        humidity REAL,
        pressure REAL,
        gas_level REAL,
        sound_level REAL
    )
    """)

    # ---- Anomaly + XAI log ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS anomalies (
        node_id TEXT PRIMARY KEY,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        parameter TEXT,
        value REAL,
        explanation TEXT
    )
    """)

    # ---- Apartment score (unchanged) ----
    c.execute("""
    CREATE TABLE IF NOT EXISTS apartment_scores (
        apartment_id TEXT PRIMARY KEY,
        last_updated DATE,
        score INTEGER,
        explanation TEXT
    )
    """)

    db.commit()
    db.close()
