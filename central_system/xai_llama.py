import ollama
import json

SYSTEM_PROMPT = """
You are an Explainable AI (XAI) module for a building safety monitoring system.

Generate a VERY SHORT and FORMAL explanation using ONLY the provided data.

Rules:
- Maximum ONE sentences.
- Explicitly mention the elevation percentage.
- Clearly state that the condition is risky or unsafe.
- Do NOT explain causes or suggest actions.
"""

def explain(context: dict) -> str:
    response = ollama.chat(
        model="llama3.2",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Summarize the following anomalies concisely, "
                    "mentioning elevation percentage and risk:\n"
                    + json.dumps(context, indent=2)
                )
            }
        ],
        options={
            "temperature": 0.1,
            "num_predict": 60
        }
    )

    return response["message"]["content"].strip()
