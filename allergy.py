"""AllerGuard AI: personalised triggers, home remedies and first-aid plan + tomorrow's dust forecast for JLT."""
import json
import re
import time

import engine

EMERGENCY = "Call 998 straight away if there is trouble breathing, swelling of the lips, tongue or throat, or fainting."

PROMPT = """You are AllerGuard AI, a careful assistant in a student allergy app for Dubai.
Using ONLY this person's answers, suggest POSSIBLE allergy triggers, home remedies and a short first-aid plan.
Never diagnose: say "possible" or "likely", never "you have". Never name medicines or doses, and suggest nothing to swallow except water.
Make every remedy and first-aid step match THEIR symptoms and triggers. Only mention dust as a trigger, tip or remedy if they selected Dust. You may use tomorrow's air-quality forecast to suggest lower-risk hours outside.
Answers: {answers}
Tomorrow's dust in JLT: {air}
Reply with ONLY valid JSON in exactly this shape:
{{"summary": "2 friendly sentences", "triggers": [{{"name": "...", "level": "Likely|Possible|Less likely", "why": "1 sentence linked to their answers"}}], "tips": ["3 to 4 short practical tips"], "remedies": ["3 to 4 simple, safe home remedies for their specific symptoms, e.g. saline nasal rinse for sneezing, cool compress for itchy eyes"], "first_aid": ["3 to 5 short steps for what to do if THEIR symptoms flare up; if they may have an inhaler or adrenaline auto-injector, say to use it as their doctor's plan says; the last step must say to call 998 for trouble breathing, swelling of the lips, tongue or throat, or fainting"]}}"""

SYMPTOM_REMEDIES = {
    "Sneezing": "Rinse your nose with a saline (salt water) spray to wash out dust and allergens.",
    "Runny nose": "Breathe in steam from a warm shower to ease a runny or stuffy nose.",
    "Itchy eyes": "Lay a cool, damp cloth over closed eyes for a few minutes, and try not to rub them.",
    "Skin itching": "Take a cool shower and wear loose cotton clothes; try not to scratch.",
    "Coughing": "Sip warm water through the day and rest in clean indoor air.",
}
TRIGGER_REMEDIES = {
    "Dust": "Wipe surfaces with a damp cloth and wash bedding weekly in hot water.",
    "Animal dander": "Wash your hands and change clothes after time with animals; keep pets out of your bedroom.",
    "Pollen / outdoor air": "Shower and change clothes after being outdoors.",
}
GENERIC_REMEDIES = list(SYMPTOM_REMEDIES.values())[:3]
SYMPTOM_AID = {
    "Itchy eyes": "Rinse your eyes gently with clean, cool water.",
    "Skin itching": "Put a cool, damp cloth on the itchy area and don't scratch.",
    "Coughing": "Sit upright and breathe slowly; if you have an inhaler, use it as your asthma plan says.",
    "Sneezing": "Blow your nose gently and rinse your face with cool water.",
}


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


def rule_triggers(a):
    ex, worse, places = set(a.get("exposures", [])), set(a.get("worse", [])), set(a.get("places", []))
    triggers = []

    def add(name, score, why):
        triggers.append({"name": name, "level": "Likely" if score >= 2 else "Possible", "why": why})

    dust = ("Dust" in ex or "Dust" in worse) * (1 + ("At home" in places))
    if dust:
        add("Dust", dust, "You said dust sets off or worsens your symptoms.")
    animals = any(x in ex for x in ("Cats", "Dogs", "Other animals")) + ("Animals" in worse) + ("Around animals" in places)
    if animals:
        add("Animal dander", animals, "You mentioned animals in your surroundings or noticed symptoms around them.")
    pollen = ("Pollen" in ex) + ("Pollen" in worse) + ("Outdoor environments" in worse) + ("Being outdoors" in ex) + ("Outdoors" in places)
    if pollen:
        add("Pollen / outdoor air", pollen, "Your symptoms seem linked to being outdoors or to pollen.")
    triggers.sort(key=lambda t: t["level"] != "Likely")
    return triggers


def rule_remedies(a, triggers):
    items = [SYMPTOM_REMEDIES[s] for s in a.get("symptoms", []) if s in SYMPTOM_REMEDIES]
    items += [TRIGGER_REMEDIES[t["name"]] for t in triggers if t["name"] in TRIGGER_REMEDIES]
    items = list(dict.fromkeys(items))[:4]
    return items or GENERIC_REMEDIES


def rule_first_aid(a, triggers):
    first = (f"Move away from your likely trigger ({triggers[0]['name'].lower()}) and get to clean indoor air."
             if triggers else "Move away from whatever seems to set off your symptoms and get to clean indoor air.")
    steps = [first] + [SYMPTOM_AID[s] for s in a.get("symptoms", []) if s in SYMPTOM_AID]
    if a.get("severity") == "Severe":
        steps.append("Because your symptoms are severe, ask a doctor about a personal allergy action plan.")
    return steps[:5] + [EMERGENCY]


TRIGGER_TIPS = {
    "Dust": "On dusty days, keep windows closed and plan outdoor time for your lower-risk hours.",
    "Animal dander": "Keep animals out of your bedroom and wash your hands after touching them.",
    "Pollen / outdoor air": "Plan outdoor time for your lower-risk hours and shower after being outside.",
}


def rule_tips(triggers):
    tips = ["Keep a short diary of symptoms, times and places to spot patterns."]
    tips += [TRIGGER_TIPS[t["name"]] for t in triggers if t["name"] in TRIGGER_TIPS]
    return tips + ["Talk to a doctor if symptoms are frequent or getting worse."]


def rule_analysis(a):
    triggers = rule_triggers(a)
    return {
        "summary": ("Here are the possible triggers that stand out from your answers."
                    if triggers else "No clear trigger stands out from your answers yet."),
        "triggers": triggers,
        "tips": rule_tips(triggers),
        "remedies": rule_remedies(a, triggers),
        "first_aid": rule_first_aid(a, triggers),
    }


def ensure_safety(data, a):
    """Fill anything the AI left out from the rules, and always end the first-aid plan with the 998 step."""
    rules = rule_analysis(a)
    for key in ("remedies", "first_aid"):
        if not isinstance(data.get(key), list) or not data[key]:
            data[key] = rules[key]
    if not any("998" in str(step) for step in data["first_aid"]):
        data["first_aid"].append(EMERGENCY)
    return data


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
    return {**ensure_safety(data, answers), "source": source, "air": air}