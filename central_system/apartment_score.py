import statistics
import datetime
from database import get_db
from xai_llama import explain


# ------------------ APARTMENT-SPECIFIC SAFE RANGES ------------------

APARTMENT_RANGES = {
    "Apt1A": {
        "temperature": (18, 28),
        "humidity": (60, 75),
        "pressure": (900, 980),
        "gas": (450, 600),
        "sound": (40, 55)
    },
    "Apt1B": {
        "temperature": (18, 30),
        "humidity": (60, 75),
        "pressure": (900, 980),
        "gas": (400, 650),
        "sound": (40, 70)
    },
    "Apt2A": {
        "temperature": (18, 30),
        "humidity": (55, 75),
        "pressure": (900, 980),
        "gas": (450, 700),
        "sound": (40, 75)
    },
    "Apt2B": {
        "temperature": (16, 28),
        "humidity": (60, 80),
        "pressure": (900, 980),
        "gas": (450, 700),
        "sound": (40, 75)
    }
}


# ------------------ RANGE-BASED SCORING FUNCTION ------------------

def range_score(value, low, high):
    """
    Improved scoring:
    - Full score in central 60% of range
    - Gentle decay near edges
    - Strong decay outside range
    """
    span = high - low
    inner_low = low + 0.2 * span
    inner_high = high - 0.2 * span

    # Ideal zone
    if inner_low <= value <= inner_high:
        return 1.0

    # Edge zones
    if low <= value < inner_low:
        return 0.7 + 0.3 * (value - low) / (inner_low - low)

    if inner_high < value <= high:
        return 0.7 + 0.3 * (high - value) / (high - inner_high)

    # Outside range
    if value < low:
        return max(0, 0.4 - (low - value) / span)

    return max(0, 0.4 - (value - high) / span)



# ------------------ MAIN SCORING LOGIC ------------------

def compute_apartment_scores():
    """
    Computes a composite safety score for all apartments based on their recent sensor history.

    This function fetches the latest 50 sensor readings for each apartment from the SQLite database.
    It evaluates the averages of these readings against predefined safe ranges for that specific apartment
    using the `range_score` function. 

    If a fire is detected in the recent history, the score immediately drops to 0. Otherwise, it 
    calculates a weighted total score (Gas: 30%, Temp: 20%, Sound: 20%, Humidity: 15%, Pressure: 15%) 
    and applies a penalty if the sensor readings are highly unstable (high standard deviation).

    Finally, it calls the local Ollama LLM (`xai_llama.explain`) to generate a human-readable 
    Explainable AI (XAI) summary of the score, and upserts the result into the database.
    """
    db = get_db()
    c = db.cursor()

    print("DB FILE USED:", db.execute("PRAGMA database_list;").fetchall())

    apartments = c.execute(
        "SELECT DISTINCT node_id FROM sensor_readings"
    ).fetchall()

    for (apt,) in apartments:

        # Skip apartments without defined ranges
        if apt not in APARTMENT_RANGES:
            continue

        rows = c.execute("""
            SELECT temperature, humidity, pressure, gas_level, sound_level, fire_state
            FROM sensor_readings
            WHERE node_id = ?
            ORDER BY timestamp DESC
            LIMIT 50
        """, (apt,)).fetchall()

        if len(rows) < 20:
            continue  # need enough history

        temps, hums, press, gas, sound, fire = zip(*rows)
        ranges = APARTMENT_RANGES[apt]

        # ------------------ FIRE OVERRIDE ------------------
        if any(fire):
            final_score = 0
            explanation = explain({
                "apartment": apt,
                "reason": "Fire detected in recent readings",
                "apartment_score": final_score
            })
        else:
            # ------------------ MEANS ------------------
            mean_temp = statistics.mean(temps)
            mean_hum = statistics.mean(hums)
            mean_press = statistics.mean(press)
            mean_gas = statistics.mean(gas)
            mean_sound = statistics.mean(sound)

            # ------------------ SCORES ------------------
            temp_score = range_score(mean_temp, *ranges["temperature"])
            hum_score = range_score(mean_hum, *ranges["humidity"])
            pressure_score = range_score(mean_press, *ranges["pressure"])
            gas_score = range_score(mean_gas, *ranges["gas"])
            sound_score = range_score(mean_sound, *ranges["sound"])

            # ------------------ STABILITY PENALTY ------------------
            instability = (
                statistics.stdev(temps) +
                statistics.stdev(gas) +
                statistics.stdev(sound)
            ) / 3

            instability_penalty = min(instability / 20, 0.15)

            # ------------------ FINAL SCORE ------------------
            total_score = (
                0.30 * gas_score +
                0.20 * temp_score +
                0.15 * hum_score +
                0.15 * pressure_score +
                0.20 * sound_score
            )

            total_score = max(0, total_score - instability_penalty)
            final_score = int(total_score * 100)

            # ------------------ XAI EXPLANATION ------------------
            explanation = explain({
                "apartment": apt,
                "average_temperature": round(mean_temp, 2),
                "average_humidity": round(mean_hum, 2),
                "average_pressure": round(mean_press, 2),
                "average_gas": round(mean_gas, 2),
                "average_sound": round(mean_sound, 2),
                "stability": "stable" if instability < 5 else "unstable",
                "apartment_score": final_score
            })

        # ------------------ UPSERT INTO DB ------------------
        c.execute("""
            INSERT INTO apartment_scores
            (apartment_id, last_updated, score, explanation)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(apartment_id)
            DO UPDATE SET
                last_updated = excluded.last_updated,
                score = excluded.score,
                explanation = excluded.explanation
        """, (
            apt,
            datetime.date.today(),
            final_score,
            explanation
        ))

    db.commit()
    db.close()


# ------------------ ENTRY POINT ------------------

if __name__ == "__main__":
    compute_apartment_scores()
