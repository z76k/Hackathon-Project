"""AllerGuard AI: AI analysis of possible allergy triggers + tomorrow's dust forecast for JLT."""
import json
import re
import time

import engine

PROMPT = """You are AllerGuard AI, a careful assistant in a student allergy app for Dubai.
Analyse this person's answers and suggest POSSIBLE allergy triggers. Never diagnose: say "possible" or "likely", never "you have".
Use tomorrow's dust forecast in your tips when it is available.
Answers: {answers}
Tomorrow's dust in JLT: {air}
Reply with ONLY valid JSON in exactly this shape:
{{"summary": "2 friendly sentences", "triggers": [{{"name": "...", "level": "Likely|Possible|Less likely", "why": "1 sentence linked to their answers"}}], "tips": ["3 to 4 short practical tips"], "remedies": ["3 to 4 simple, safe home remedies such as a saline nasal rinse, steam, a cool compress for itchy eyes or washing bedding in hot water; no medicines, herbs to swallow or doses"]}}"""


def air_summary(answers):
    try:
        pm, hours, _ = engine.forecast_tomorrow()
    except Exception as e:
        print(f"Dust forecast failed: {e}")
        return None
    lim = engine.personal_limits(answers)
    risk = "Higher" if pm > lim["pm_limit"] else "Moderate" if pm > lim["pm_limit"] * 0.75 else "Lower"
    windows, _ = engine.lower_risk_windows(hours, lim)
    return {"pm_tomorrow": round(pm, 1), "pm_limit": lim["pm_limit"], "risk": risk,
            "reasons": lim["reasons"], "windows": windows}


def rule_analysis(a):
    ex, worse, places = set(a.get("exposures", [])), set(a.get("worse", [])), set(a.get("places", []))
    triggers = []

    def add(name, score, why):
        triggers.append({"name": name, "level": "Likely" if score >= 2 else "Possible", "why": why})

    dust = ("Dust" in ex) + ("Dust" in worse) + ("At home" in places)
    if dust:
        add("Dust", dust, "Dust came up in what you're around, what makes symptoms worse, or symptoms at home.")
    animals = any(x in ex for x in ("Cats", "Dogs", "Other animals")) + ("Animals" in worse) + ("Around animals" in places)
    if animals:
        add("Animal dander", animals, "You mentioned animals in your surroundings or noticed symptoms around them.")
    pollen = ("Pollen" in ex) + ("Pollen" in worse) + ("Outdoor environments" in worse) + ("Outdoors" in places)
    if pollen:
        add("Pollen / outdoor air", pollen, "Your symptoms seem linked to being outdoors or to pollen.")
    tips = ["Keep a short diary of symptoms, times and places to spot patterns.",
            "On dusty days, keep windows closed and clean with a damp cloth.",
            "Talk to a doctor if symptoms are frequent or getting worse."]
    summary = ("Here are the possible triggers that stand out from your answers."
               if triggers else "No clear trigger stands out from your answers yet.")
    triggers.sort(key=lambda t: t["level"] != "Likely")
    remedies = ["Rinse your nose with a saline (salt water) spray to clear dust and allergens.",
                "Lay a cool, damp cloth over itchy eyes for a few minutes.",
                "Breathe in steam from a warm shower to ease a stuffy nose.",
                "Wash bedding weekly in hot water to reduce dust mites."]
    return {"summary": summary, "triggers": triggers, "tips": tips, "remedies": remedies}


def ai_analysis(answers, air):
    if engine.client is None:
        return None, "rules"
    air_text = (f"PM2.5 forecast {air['pm_tomorrow']} µg/m³, their limit {air['pm_limit']}, "
                f"{air['risk']} risk, lower-risk hours outside {air['windows'] or 'none'}") if air else "not available"
    prompt = PROMPT.format(answers=json.dumps(answers, ensure_ascii=False), air=air_text)
    start = time.time()
    for m in engine.LLM_MODELS:
        if time.time() - start > 20:
            break
        try:
            text = engine.client.models.generate_content(model=m, contents=prompt).text or ""
            data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            if isinstance(data.get("triggers"), list) and data.get("tips"):
                return data, m
        except Exception as e:
            print(f"{m} failed: {e}")
    return None, "rules"


def analyze(answers):
    air = air_summary(answers)
    data, source = ai_analysis(answers, air)
    if data is None:
        data = rule_analysis(answers)
    return {**data, "source": source, "air": air}