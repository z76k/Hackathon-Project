"""AllerGuard AI engine: real JLT air data, ML forecast, personal risk and Cloudy's advice."""
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from google import genai
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

load_dotenv()

LAT, LON, TZ = 25.0693, 55.1413, "Asia/Dubai"  # Jumeirah Lakes Towers, Dubai
DATA_FILE = Path("data/jlt_daily.csv")
AGG = {"pm2_5": "mean", "pm10": "mean", "dust": "mean", "temperature_2m": "mean",
       "relative_humidity_2m": "mean", "wind_speed_10m": "max", "precipitation": "sum"}
FEATURES = ["pm2_5", "pm10", "dust", "temperature_2m", "relative_humidity_2m",
            "wind_speed_10m", "precipitation", "pm2_5_avg7", "pm2_5_change", "month"]
LLM_MODELS = ["gemini-3.5-flash-lite", "gemma-4-26b-a4b-it", "gemma-4-31b-it"]

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key, http_options={"timeout": 10_000}) if api_key else None


# ---------- 1. Data ----------
def fetch(url, params, tries=3):
    for attempt in range(tries):
        try:
            data = requests.get(url, params=params, timeout=90).json()
            break
        except requests.RequestException as err:
            print(f"Open-Meteo attempt {attempt + 1} failed: {err.__class__.__name__}")
            if attempt == tries - 1:
                raise
            time.sleep(1.5)
    if "hourly" not in data:
        raise RuntimeError(f"Open-Meteo error: {data}")
    return data


def get_history(start="2023-01-01", end="2026-11-12"):
    if DATA_FILE.exists():
        return pd.read_csv(DATA_FILE, index_col="time", parse_dates=True)
    base = {"latitude": LAT, "longitude": LON, "timezone": TZ, "start_date": start, "end_date": end}
    air = fetch("https://air-quality-api.open-meteo.com/v1/air-quality",
                {**base, "hourly": "pm2_5,pm10,dust"})
    weather = fetch("https://archive-api.open-meteo.com/v1/archive",
                    {**base, "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation"})
    df = pd.DataFrame(air["hourly"]).merge(pd.DataFrame(weather["hourly"]), on="time")
    df["time"] = pd.to_datetime(df["time"])
    daily = df.set_index("time").resample("D").agg(AGG).dropna()
    DATA_FILE.parent.mkdir(exist_ok=True)
    daily.to_csv(DATA_FILE)
    return daily


def add_features(daily):
    d = daily.asfreq("D").copy()
    d["pm2_5_avg7"] = d["pm2_5"].rolling(7).mean()
    d["pm2_5_change"] = d["pm2_5"].diff()
    d["month"] = d.index.month
    return d


# ---------- 2. Model ----------
def train_model():
    data = add_features(get_history())
    data["tomorrow_pm2_5"] = data["pm2_5"].shift(-1)
    data = data.dropna()
    train, test = data[data.index < "2026-01-01"], data[data.index >= "2026-01-01"]
    model = RandomForestRegressor(n_estimators=300, min_samples_leaf=5, random_state=42)
    model.fit(train[FEATURES], train["tomorrow_pm2_5"])
    pred = model.predict(test[FEATURES])
    results = {
        "train_days": len(train), "test_days": len(test),
        "mae_baseline": round(mean_absolute_error(test["tomorrow_pm2_5"], test["pm2_5"]), 1),
        "mae_model": round(mean_absolute_error(test["tomorrow_pm2_5"], pred), 1),
    }
    return model, results


MODEL, RESULTS = train_model()


# ---------- 3. Live forecast ----------
def get_live():
    common = {"latitude": LAT, "longitude": LON, "timezone": TZ, "past_days": 8, "forecast_days": 2}
    w = fetch("https://api.open-meteo.com/v1/forecast", {**common,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m",
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,apparent_temperature"})
    a = fetch("https://air-quality-api.open-meteo.com/v1/air-quality", {**common,
        "current": "us_aqi,pm2_5,dust,uv_index",
        "hourly": "pm2_5,pm10,dust,uv_index"})
    hours = pd.DataFrame(w["hourly"]).merge(pd.DataFrame(a["hourly"]), on="time")
    hours["time"] = pd.to_datetime(hours["time"])
    return hours, {**w["current"], **a["current"]}


_live_cache = {"at": 0.0, "data": None}


def get_live_cached(max_age=600):
    """Reuse live data for 10 minutes so every request doesn't refetch it."""
    if _live_cache["data"] is None or time.time() - _live_cache["at"] > max_age:
        _live_cache["data"], _live_cache["at"] = get_live(), time.time()
    return _live_cache["data"]


def forecast_tomorrow():
    hours, now = get_live_cached()
    daily = add_features(hours.set_index("time").resample("D").agg(AGG))
    today = pd.Timestamp.now(tz=TZ).normalize().tz_localize(None)
    pm_tomorrow = float(MODEL.predict(daily.loc[[today], FEATURES])[0])
    tomorrow_hours = hours[hours["time"].dt.normalize() == today + pd.Timedelta(days=1)]
    return pm_tomorrow, tomorrow_hours, now


# ---------- 4. Personal risk ----------
def personal_limits(a):
    age = a.get("age", "")
    exposures, worse = set(a.get("exposures", [])), set(a.get("worse", []))
    outdoors = "Outdoors" in a.get("places", []) or "Being outdoors" in exposures or "Outdoor environments" in worse
    reasons = []
    if age in ("Under 13", "13–17"):
        reasons.append("children and teens are more sensitive to polluted air")
    if age == "Over 50":
        reasons.append("older adults are more sensitive to polluted air")
    if "Dust" in exposures or "Dust" in worse:
        reasons.append("you said dust affects you")
    if "Coughing" in a.get("symptoms", []):
        reasons.append("you reported coughing")
    if a.get("severity") in ("Moderate", "Severe"):
        reasons.append(f"your symptoms are {a['severity'].lower()}")
    if outdoors:
        reasons.append("you spend time outdoors")
    heat_sensitive = age in ("Under 13", "Over 50") or outdoors
    return {"sensitive_air": bool(reasons), "reasons": reasons, "heat_sensitive": heat_sensitive,
            "pm_limit": 35.4 if reasons else 55.4, "feels_limit": 32 if heat_sensitive else 41}


def lower_risk_windows(hours, lim):
    day = hours[(hours["time"].dt.hour >= 6) & (hours["time"].dt.hour <= 21)].copy()
    day["ok"] = ((day["pm2_5"] < lim["pm_limit"]) &
                 (day["apparent_temperature"] < lim["feels_limit"]) & (day["uv_index"] < 8))
    windows, start = [], None
    for t, ok in zip(day["time"], day["ok"]):
        if ok and start is None:
            start = t
        if not ok and start is not None:
            windows.append(f"{start:%H:%M}–{t:%H:%M}")
            start = None
    if start is not None:
        windows.append(f"{start:%H:%M}–22:00")
    return windows, day


# ---------- 5. Cloudy's advice ----------
def template_advice(r):
    hours = ", ".join(r["windows"]) or "none tomorrow"
    why = f"because {r['reasons'][0]}" if r["reasons"] else "for most healthy adults"
    return (f"Tomorrow looks like {r['risk'].lower()} for you: PM2.5 is forecast at {r['pm_tomorrow']}, "
            f"and your limit is {r['pm_limit']} {why}. Lower-risk hours outside: {hours}. "
            f"Keep water with you and check again in the morning!")


def mascot_advice(r, budget=20):
    if client is None:
        return template_advice(r), "template"
    prompt = f"""You are Cloudy, a cheerful cloud mascot in AllerGuard AI, a Dubai dust and allergy app.
Using ONLY these facts, write 3 short, friendly sentences (max 60 words): this person's risk tomorrow and why,
the best hours to be outside, and one practical precaution. Say "higher risk" or "lower risk", never "safe".
Never diagnose. Facts: forecast PM2.5 tomorrow in JLT {r['pm_tomorrow']} µg/m³; personal limit {r['pm_limit']};
risk {r['risk']}; reasons {r['reasons'] or 'none'}; lower-risk hours {r['windows'] or 'none'};
max feels-like {r['max_feels']}°C; max UV {r['max_uv']}."""
    start = time.time()
    for m in LLM_MODELS:
        if time.time() - start > budget:
            break
        try:
            reply = client.models.generate_content(model=m, contents=prompt)
            if reply.text:
                return reply.text.strip(), m
        except Exception as e:
            print(f"{m} failed: {e}")
    return template_advice(r), "template"


# ---------- 6. The one function the website calls ----------
def analyze(answers):
    if answers.get("severe"):
        return {"urgent": True, "message": "Breathing difficulty or severe symptoms need real medical help, "
                "not an app. Tell a trusted adult and contact a doctor, or call 998 in an emergency."}
    pm, hours, now = forecast_tomorrow()
    lim = personal_limits(answers)
    if pm > lim["pm_limit"]:
        risk = "Higher risk"
    elif pm > lim["pm_limit"] * 0.75:
        risk = "Moderate risk"
    else:
        risk = "Lower risk"
    windows, day = lower_risk_windows(hours, lim)
    r = {"urgent": False, "pm_tomorrow": round(pm, 1), "risk": risk, **lim, "windows": windows,
         "max_feels": round(float(day["apparent_temperature"].max()), 1),
         "max_uv": round(float(day["uv_index"].max()), 1), "now": now,
         "hourly": [{"hour": f"{t:%H}", "pm2_5": round(float(p), 1), "ok": bool(ok)}
                    for t, p, ok in zip(day["time"], day["pm2_5"], day["ok"])]}
    r["advice"], r["advice_model"] = mascot_advice(r)
    return r


if __name__ == "__main__":
    print("Model results:", RESULTS)
    print(analyze({"age": "13–17", "exposures": ["Dust"], "symptoms": ["Sneezing"]}))