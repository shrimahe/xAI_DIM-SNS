def compute_safety_score(temp, gas, sound):
    risk = 0.4 * gas + 0.3 * temp + 0.3 * sound
    return max(0, int(100 - risk))
