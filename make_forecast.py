"""Runs the ML model and saves tomorrow's dust forecast for the GitHub Pages site (docs/forecast.json)."""
import json
import math
from pathlib import Path

import pandas as pd

import engine


def num(x):
    x = float(x)
    return None if math.isnan(x) else round(x, 1)


pm, hours, _ = engine.forecast_tomorrow()
day = hours[(hours["time"].dt.hour >= 6) & (hours["time"].dt.hour <= 21)]
tomorrow = pd.Timestamp.now(tz=engine.TZ).normalize() + pd.Timedelta(days=1)
out = {
    "for_date": tomorrow.strftime("%a %d %b %Y"),
    "generated": pd.Timestamp.now(tz=engine.TZ).strftime("%Y-%m-%d %H:%M"),
    "pm_tomorrow": round(pm, 1),
    "model_results": engine.RESULTS,
    "hourly": [{"hour": int(t.hour), "pm2_5": num(p), "feels": num(f), "uv": num(u)}
               for t, p, f, u in zip(day["time"], day["pm2_5"], day["apparent_temperature"], day["uv_index"])],
}
Path("docs").mkdir(exist_ok=True)
Path("docs/forecast.json").write_text(json.dumps(out, indent=1))
print("Saved forecast for", out["for_date"], "| PM2.5", out["pm_tomorrow"])