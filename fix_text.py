from pathlib import Path

PY_JOIN = '(", ".join(reasons[:-1]) + " and " + reasons[-1] if len(reasons) > 1 else "".join(reasons))'
JS_JOIN = '(reasons.length > 1 ? reasons.slice(0, -1).join(", ") + " and " + reasons[reasons.length - 1] : reasons.join(""))'
DUST_TIP_OLD = "On dusty days, keep windows closed and plan outdoor time for your lower-risk hours."
DUST_TIP_NEW = "On dusty days, keep windows closed and wear a light mask if you go out."

EDITS = {
    "engine.py": [('", ".join(reasons)', PY_JOIN)],
    "build_pages.py": [('reasons.join(", ")', JS_JOIN), (DUST_TIP_OLD, DUST_TIP_NEW)],
    "allergy.py": [(DUST_TIP_OLD, DUST_TIP_NEW)],
    "templates/index.html": [
        ("machine learning dust forecast", "machine learning air-quality (PM2.5) forecast"),
        ("Dust data: Open-Meteo", "Air data: Open-Meteo"),
    ],
}

for path, edits in EDITS.items():
    p = Path(path)
    text = p.read_text()
    for old, new in edits:
        n = text.count(old)
        print(f"{path}: {old[:40]!r} → {n} found")
        text = text.replace(old, new)
    p.write_text(text)