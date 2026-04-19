import sqlite3
import matplotlib.pyplot as plt
import sys


# ------------------ CONFIG ------------------

import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "safety_xai.db")


# ------------------ DB UTILITIES ------------------

def get_connection():
    try:
        return sqlite3.connect(DB_PATH)
    except Exception as e:
        print("❌ Failed to connect to database:", e)
        sys.exit(1)


def detect_sensor_table(cursor):
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table'
    """)
    tables = [t[0] for t in cursor.fetchall()]

    for name in ["sensor_readings", "sensor_data", "sensor_logs", "readings"]:
        if name in tables:
            return name

    print("❌ No sensor table found.")
    print("Available tables:", tables)
    sys.exit(1)


def get_all_apartments(cursor, table):
    cursor.execute(f"SELECT DISTINCT node_id FROM {table}")
    return [row[0] for row in cursor.fetchall()]


# ------------------ DATA FETCH ------------------

def fetch_apartment_data(cursor, table, apartment_id, limit):
    cursor.execute(f"""
        SELECT temperature, humidity, pressure, gas_level, sound_level
        FROM {table}
        WHERE node_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (apartment_id, limit))

    rows = cursor.fetchall()
    if not rows:
        return None

    rows.reverse()  # oldest → newest

    temps, hums, press, gas, sound = zip(*rows)
    samples = list(range(1, len(rows) + 1))

    return {
        "samples": samples,
        "temperature": temps,
        "humidity": hums,
        "pressure": press,
        "gas": gas,
        "sound": sound
    }


# ------------------ PLOTTING ------------------

def plot_parameter(apartment_data, parameter, ylabel, title):
    plt.figure(figsize=(10, 5))

    for apt, data in apartment_data.items():
        plt.plot(
            data["samples"],
            data[parameter],
            linewidth=1,
            label=apt
        )

    plt.xlabel("Sample Number")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def plot_all_parameters(limit):
    conn = get_connection()
    cursor = conn.cursor()

    table = detect_sensor_table(cursor)
    print(f"✔ Using table: {table}")

    apartments = get_all_apartments(cursor, table)
    print("✔ Apartments found:", apartments)

    apartment_data = {}

    for apt in apartments:
        data = fetch_apartment_data(cursor, table, apt, limit)
        if data:
            apartment_data[apt] = data

    if not apartment_data:
        print("❌ No data available to plot.")
        sys.exit(1)

    plot_parameter(apartment_data, "temperature",
                   "Temperature (°C)", "Temperature vs Sample Number")

    plot_parameter(apartment_data, "humidity",
                   "Humidity (%)", "Humidity vs Sample Number")

    plot_parameter(apartment_data, "pressure",
                   "Pressure (hPa)", "Pressure vs Sample Number")

    plot_parameter(apartment_data, "gas",
                   "Gas Level", "Gas Level vs Sample Number")

    plot_parameter(apartment_data, "sound",
                   "Sound Level (dB)", "Sound Level vs Sample Number")

    conn.close()


# ------------------ ENTRY POINT ------------------

if __name__ == "__main__":
    try:
        limit = int(input("How many recent readings to plot per apartment?: "))
        plot_all_parameters(limit)
    except ValueError:
        print("❌ Please enter a valid number.")
