"""Sends test profiles to the running server and checks the personal limits."""
import requests

URL = "http://127.0.0.1:5050/api/analyze"
CASES = [
    ("Teen with dust",  {"age": "13–17", "exposures": ["Dust"]}, lambda r: r["pm_limit"] == 35.4),
    ("Healthy adult",   {"age": "31–50"},                       lambda r: r["pm_limit"] == 55.4),
    ("Older adult",     {"age": "Over 50"},                     lambda r: r["pm_limit"] == 35.4 and r["heat_sensitive"]),
    ("Outdoor runner",  {"age": "18–30", "places": ["Outdoors"]}, lambda r: r["feels_limit"] == 32),
    ("Severe symptoms", {"severe": True},                       lambda r: r["urgent"]),
    ("Empty answers",   {},                                     lambda r: r["pm_limit"] == 55.4),
]

passed = 0
for name, answers, check in CASES:
    try:
        r = requests.post(URL, json=answers, timeout=120).json()
        ok = bool(check(r))
    except Exception as e:
        r, ok = {"error": str(e)}, False
    passed += ok
    if r.get("urgent"):
        summary = "medical-help message shown"
    else:
        summary = f"{r.get('risk')} | limit {r.get('pm_limit')} | advice by {r.get('advice_model')} | {r.get('error', '')}"
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {summary}")
print(f"\n{passed}/{len(CASES)} passed")
