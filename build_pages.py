"""Builds the GitHub Pages version (docs/index.html) from templates/index.html.
GitHub Pages can't run Python, so the AI analysis runs in the browser through a Cloudflare Worker
(AI_PROXY_URL in .env) that keeps the API key secret. Without a Worker, the page uses the
rule-based backup. The ML dust forecast comes from docs/forecast.json (updated daily by a GitHub Action)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
PROXY = os.getenv("AI_PROXY_URL", "")

BROWSER_JS = r'''
    // ---------- GitHub Pages version: AI through a Cloudflare Worker ----------
    const AI_PROXY = "__AI_PROXY__";
    const MODELS = ["gemini-3.5-flash-lite", "gemma-4-26b-a4b-it", "gemma-4-31b-it"];
    const EMERGENCY = "Call 998 straight away if there is trouble breathing, swelling of the lips, tongue or throat, or fainting.";
    const SYMPTOM_REMEDIES = {
      "Sneezing": "Rinse your nose with a saline (salt water) spray to wash out dust and allergens.",
      "Runny nose": "Breathe in steam from a warm shower to ease a runny or stuffy nose.",
      "Itchy eyes": "Lay a cool, damp cloth over closed eyes for a few minutes, and try not to rub them.",
      "Skin itching": "Take a cool shower and wear loose cotton clothes; try not to scratch.",
      "Coughing": "Sip warm water through the day and rest in clean indoor air.",
    };
    const TRIGGER_REMEDIES = {
      "Dust": "Wipe surfaces with a damp cloth and wash bedding weekly in hot water.",
      "Animal dander": "Wash your hands and change clothes after time with animals; keep pets out of your bedroom.",
      "Pollen / outdoor air": "Shower and change clothes after being outdoors.",
    };
    const GENERIC_REMEDIES = [SYMPTOM_REMEDIES["Sneezing"], SYMPTOM_REMEDIES["Runny nose"], SYMPTOM_REMEDIES["Itchy eyes"]];
    const SYMPTOM_AID = {
      "Itchy eyes": "Rinse your eyes gently with clean, cool water.",
      "Skin itching": "Put a cool, damp cloth on the itchy area and don't scratch.",
      "Coughing": "Sit upright and breathe slowly; if you have an inhaler, use it as your asthma plan says.",
      "Sneezing": "Blow your nose gently and rinse your face with cool water.",
    };
    const forecastReady = fetch("forecast.json", { cache: "no-store" }).then((r) => r.json()).catch(() => null);
    const pad = (n) => String(n).padStart(2, "0");

    function personalLimits(a) {
      const outdoors = a.places.includes("Outdoors") || a.exposures.includes("Being outdoors") || a.worse.includes("Outdoor environments");
      const reasons = [];
      if (["Under 13", "13–17"].includes(a.age)) reasons.push("children and teens are more sensitive to polluted air");
      if (a.age === "Over 50") reasons.push("older adults are more sensitive to polluted air");
      if (a.exposures.includes("Dust") || a.worse.includes("Dust")) reasons.push("you said dust affects you");
      if (a.symptoms.includes("Coughing")) reasons.push("you reported coughing");
      if (["Moderate", "Severe"].includes(a.severity)) reasons.push(`your symptoms are ${a.severity.toLowerCase()}`);
      if (outdoors) reasons.push("you spend time outdoors");
      const heat = ["Under 13", "Over 50"].includes(a.age) || outdoors;
      return { reasons, pmLimit: reasons.length ? 35.4 : 55.4, feelsLimit: heat ? 32 : 41 };
    }

    function lowerRiskWindows(hours, lim) {
      const out = [];
      let start = null;
      for (const h of hours) {
        const ok = h.pm2_5 != null && h.pm2_5 < lim.pmLimit && (h.feels == null || h.feels < lim.feelsLimit) && (h.uv == null || h.uv < 8);
        if (ok && start === null) start = h.hour;
        if (!ok && start !== null) { out.push(`${pad(start)}:00–${pad(h.hour)}:00`); start = null; }
      }
      if (start !== null) out.push(`${pad(start)}:00–22:00`);
      return out;
    }

    function airSummary(a, f) {
      if (!f) return null;
      const lim = personalLimits(a), pm = f.pm_tomorrow;
      const risk = pm > lim.pmLimit ? "Higher" : pm > lim.pmLimit * 0.75 ? "Moderate" : "Lower";
      return { pm_tomorrow: pm, pm_limit: lim.pmLimit, risk, reasons: lim.reasons,
               windows: lowerRiskWindows(f.hourly, lim), for_date: f.for_date };
    }

    function ruleTriggers(a) {
      const triggers = [];
      const add = (name, score, why) => triggers.push({ name, level: score >= 2 ? "Likely" : "Possible", why });
      const count = (checks) => checks.filter(Boolean).length;
      const dust = (a.exposures.includes("Dust") || a.worse.includes("Dust")) ? 1 + (a.places.includes("At home") ? 1 : 0) : 0;
      if (dust) add("Dust", dust, "You said dust sets off or worsens your symptoms.");
      const animals = count([["Cats", "Dogs", "Other animals"].some((x) => a.exposures.includes(x)), a.worse.includes("Animals"), a.places.includes("Around animals")]);
      if (animals) add("Animal dander", animals, "You mentioned animals in your surroundings or noticed symptoms around them.");
      const pollen = count([a.exposures.includes("Pollen"), a.worse.includes("Pollen"), a.worse.includes("Outdoor environments"), a.exposures.includes("Being outdoors"), a.places.includes("Outdoors")]);
      if (pollen) add("Pollen / outdoor air", pollen, "Your symptoms seem linked to being outdoors or to pollen.");
      return triggers.sort((x, y) => (x.level === "Likely" ? 0 : 1) - (y.level === "Likely" ? 0 : 1));
    }

    function ruleRemedies(a, triggers) {
      const items = [...a.symptoms.map((s) => SYMPTOM_REMEDIES[s]), ...triggers.map((t) => TRIGGER_REMEDIES[t.name])].filter(Boolean);
      const unique = [...new Set(items)].slice(0, 4);
      return unique.length ? unique : GENERIC_REMEDIES;
    }

    function ruleFirstAid(a, triggers) {
      const steps = [triggers.length
        ? `Move away from your likely trigger (${triggers[0].name.toLowerCase()}) and get to clean indoor air.`
        : "Move away from whatever seems to set off your symptoms and get to clean indoor air."];
      a.symptoms.forEach((s) => SYMPTOM_AID[s] && steps.push(SYMPTOM_AID[s]));
      if (a.severity === "Severe") steps.push("Because your symptoms are severe, ask a doctor about a personal allergy action plan.");
      return [...steps.slice(0, 5), EMERGENCY];
    }

    const TRIGGER_TIPS = {
      "Dust": "On dusty days, keep windows closed and plan outdoor time for your lower-risk hours.",
      "Animal dander": "Keep animals out of your bedroom and wash your hands after touching them.",
      "Pollen / outdoor air": "Plan outdoor time for your lower-risk hours and shower after being outside.",
    };
    function ruleTips(triggers) {
      return ["Keep a short diary of symptoms, times and places to spot patterns.",
              ...triggers.map((t) => TRIGGER_TIPS[t.name]).filter(Boolean),
              "Talk to a doctor if symptoms are frequent or getting worse."];
    }

    function ruleAnalysis(a) {
      const triggers = ruleTriggers(a);
      return {
        summary: triggers.length ? "Here are the possible triggers that stand out from your answers." : "No clear trigger stands out from your answers yet.",
        triggers,
        tips: ruleTips(triggers),
        remedies: ruleRemedies(a, triggers),
        first_aid: ruleFirstAid(a, triggers),
      };
    }

    function ensureSafety(r, a) {
      const rules = ruleAnalysis(a);
      for (const key of ["remedies", "first_aid"]) {
        if (!Array.isArray(r[key]) || !r[key].length) r[key] = rules[key];
      }
      if (!r.first_aid.some((s) => String(s).includes("998"))) r.first_aid.push(EMERGENCY);
      return r;
    }

    function buildPrompt(a, airText) {
      return `You are AllerGuard AI, a careful assistant in a student allergy app for Dubai.
Using ONLY this person's answers, suggest POSSIBLE allergy triggers, home remedies and a short first-aid plan.
Never diagnose: say "possible" or "likely", never "you have". Never name medicines or doses, and suggest nothing to swallow except water.
Make every remedy and first-aid step match THEIR symptoms and triggers. Only mention dust as a trigger, tip or remedy if they selected Dust. You may use tomorrow's air-quality forecast to suggest lower-risk hours outside.
Answers: ${JSON.stringify(a)}
Tomorrow's dust in JLT: ${airText}
Reply with ONLY valid JSON in exactly this shape:
{"summary": "2 friendly sentences", "triggers": [{"name": "...", "level": "Likely|Possible|Less likely", "why": "1 sentence linked to their answers"}], "tips": ["3 to 4 short practical tips"], "remedies": ["3 to 4 simple, safe home remedies for their specific symptoms, e.g. saline nasal rinse for sneezing, cool compress for itchy eyes"], "first_aid": ["3 to 5 short steps for what to do if THEIR symptoms flare up; if they may have an inhaler or adrenaline auto-injector, say to use it as their doctor's plan says; the last step must say to call 998 for trouble breathing, swelling of the lips, tongue or throat, or fainting"]}`;
    }

    async function aiAnalysis(a, air) {
      if (!AI_PROXY) return null;
      const airText = air ? `PM2.5 forecast ${air.pm_tomorrow} µg/m³, their limit ${air.pm_limit}, ${air.risk} risk, lower-risk hours outside ${air.windows.join(", ") || "none"}` : "not available";
      const prompt = buildPrompt(a, airText);
      const started = Date.now();
      for (const m of MODELS) {
        if (Date.now() - started > 20000) break;
        try {
          const ctrl = new AbortController();
          const timer = setTimeout(() => ctrl.abort(), 12000);
          const res = await fetch(AI_PROXY, {
            method: "POST", headers: { "Content-Type": "application/json" }, signal: ctrl.signal,
            body: JSON.stringify({ model: m, prompt }),
          });
          clearTimeout(timer);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          const parts = (data.candidates && data.candidates[0] && data.candidates[0].content && data.candidates[0].content.parts) || [];
          const text = parts.filter((p) => !p.thought).map((p) => p.text || "").join("");
          const parsed = JSON.parse(text.match(/\{[\s\S]*\}/)[0]);
          if (Array.isArray(parsed.triggers) && parsed.tips) return { ...parsed, source: m };
        } catch (e) {
          console.warn(m, "failed:", e.message);
        }
      }
      return null;
    }

    async function finish() {
      quiz.innerHTML = `<div class="progress"><i style="width:100%"></i></div><div class="loading"><div class="spinner"></div>AllerGuard AI is analysing your answers…</div>`;
      document.getElementById("results").classList.remove("show");
      const payload = {
        age: answers.age || "", symptoms: answers.symptoms || [], severity: answers.severity || "",
        exposures: answers.exposures || [], worse: answers.worse || [], places: answers.places || [],
      };
      const air = airSummary(payload, await forecastReady);
      const ai = await aiAnalysis(payload, air);
      const r = ensureSafety({ ...(ai || { ...ruleAnalysis(payload), source: "rules" }), air }, payload);
      quiz.innerHTML = `<div class="progress"><i style="width:100%"></i></div><p class="q-meta" style="text-align:center">✓ Analysis complete. Your results are below.</p>`;
      showResults(renderResults(r));
    }

'''

page = Path("templates/index.html").read_text()
start = page.index("    async function finish() {")
end = page.index("    function renderResults(r) {")
page = page[:start] + BROWSER_JS.lstrip("\n").replace("__AI_PROXY__", PROXY) + page[end:]
page = page.replace('<div class="big">${a.pm_tomorrow} <small>µg/m³ PM2.5</small></div>',
                    '<div class="big">${a.pm_tomorrow} <small>µg/m³ PM2.5</small></div>'
                    '${a.for_date ? `<p style="margin:-4px 0 8px">Forecast for ${esc(a.for_date)}</p>` : ""}', 1)
Path("docs").mkdir(exist_ok=True)
Path("docs/index.html").write_text(page)
print("Built docs/index.html | AI proxy:", PROXY or "none yet (rule-based backup)")