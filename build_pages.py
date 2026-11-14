"""Builds the GitHub Pages version (docs/index.html) from templates/index.html.
On Pages there is no Python server, so the AI analysis runs in the browser and the
ML dust forecast is read from docs/forecast.json (updated daily by a GitHub Action)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("GEMINI_API_KEY", "")

BROWSER_JS = r'''
    // ---------- GitHub Pages version: the AI runs in the browser ----------
    const GEMINI_KEY = "__GEMINI_KEY__";
    const MODELS = ["gemini-3.5-flash-lite", "gemma-4-26b-a4b-it", "gemma-4-31b-it"];
    const RULE_REMEDIES = [
      "Rinse your nose with a saline (salt water) spray to clear dust and allergens.",
      "Lay a cool, damp cloth over itchy eyes for a few minutes.",
      "Breathe in steam from a warm shower to ease a stuffy nose.",
      "Wash bedding weekly in hot water to reduce dust mites.",
    ];
    const forecastReady = fetch("forecast.json", { cache: "no-store" }).then((r) => r.json()).catch(() => null);
    const pad = (n) => String(n).padStart(2, "0");

    function personalLimits(a) {
      const outdoors = a.places.includes("Outdoors") || a.worse.includes("Outdoor environments");
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

    function ruleAnalysis(a) {
      const triggers = [];
      const add = (name, score, why) => triggers.push({ name, level: score >= 2 ? "Likely" : "Possible", why });
      const count = (checks) => checks.filter(Boolean).length;
      const dust = count([a.exposures.includes("Dust"), a.worse.includes("Dust"), a.places.includes("At home")]);
      if (dust) add("Dust", dust, "Dust came up in what you're around, what makes symptoms worse, or symptoms at home.");
      const animals = count([["Cats", "Dogs", "Other animals"].some((x) => a.exposures.includes(x)), a.worse.includes("Animals"), a.places.includes("Around animals")]);
      if (animals) add("Animal dander", animals, "You mentioned animals in your surroundings or noticed symptoms around them.");
      const pollen = count([a.exposures.includes("Pollen"), a.worse.includes("Pollen"), a.worse.includes("Outdoor environments"), a.places.includes("Outdoors")]);
      if (pollen) add("Pollen / outdoor air", pollen, "Your symptoms seem linked to being outdoors or to pollen.");
      triggers.sort((x, y) => (x.level === "Likely" ? 0 : 1) - (y.level === "Likely" ? 0 : 1));
      return {
        summary: triggers.length ? "Here are the possible triggers that stand out from your answers." : "No clear trigger stands out from your answers yet.",
        triggers,
        tips: ["Keep a short diary of symptoms, times and places to spot patterns.",
               "On dusty days, keep windows closed and clean with a damp cloth.",
               "Talk to a doctor if symptoms are frequent or getting worse."],
        remedies: RULE_REMEDIES,
      };
    }

    function buildPrompt(a, airText) {
      return `You are AllerGuard AI, a careful assistant in a student allergy app for Dubai.
Analyse this person's answers and suggest POSSIBLE allergy triggers. Never diagnose: say "possible" or "likely", never "you have".
Use tomorrow's dust forecast in your tips when it is available.
Answers: ${JSON.stringify(a)}
Tomorrow's dust in JLT: ${airText}
Reply with ONLY valid JSON in exactly this shape:
{"summary": "2 friendly sentences", "triggers": [{"name": "...", "level": "Likely|Possible|Less likely", "why": "1 sentence linked to their answers"}], "tips": ["3 to 4 short practical tips"], "remedies": ["3 to 4 simple, safe home remedies such as a saline nasal rinse, steam, a cool compress for itchy eyes or washing bedding in hot water; no medicines, herbs to swallow or doses"]}`;
    }

    async function aiAnalysis(a, air) {
      if (!GEMINI_KEY) return null;
      const airText = air ? `PM2.5 forecast ${air.pm_tomorrow} µg/m³, their limit ${air.pm_limit}, ${air.risk} risk, lower-risk hours outside ${air.windows.join(", ") || "none"}` : "not available";
      const prompt = buildPrompt(a, airText);
      const started = Date.now();
      for (const m of MODELS) {
        if (Date.now() - started > 20000) break;
        try {
          const ctrl = new AbortController();
          const timer = setTimeout(() => ctrl.abort(), 12000);
          const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${m}:generateContent?key=${encodeURIComponent(GEMINI_KEY)}`, {
            method: "POST", headers: { "Content-Type": "application/json" }, signal: ctrl.signal,
            body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }),
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
      const r = { ...(ai || { ...ruleAnalysis(payload), source: "rules" }), air };
      if (!r.remedies || !r.remedies.length) r.remedies = RULE_REMEDIES;
      quiz.innerHTML = `<div class="progress"><i style="width:100%"></i></div><p class="q-meta" style="text-align:center">✓ Analysis complete. Your results are below.</p>`;
      showResults(renderResults(r));
    }

'''

page = Path("templates/index.html").read_text()
start = page.index("    async function finish() {")
end = page.index("    function renderResults(r) {")
page = page[:start] + BROWSER_JS.lstrip("\n").replace("__GEMINI_KEY__", KEY) + page[end:]
page = page.replace('<div class="big">${a.pm_tomorrow} <small>µg/m³ PM2.5</small></div>',
                    '<div class="big">${a.pm_tomorrow} <small>µg/m³ PM2.5</small></div>'
                    '${a.for_date ? `<p style="margin:-4px 0 8px">Forecast for ${esc(a.for_date)}</p>` : ""}', 1)
Path("docs").mkdir(exist_ok=True)
Path("docs/index.html").write_text(page)
print("Built docs/index.html | key inserted:", bool(KEY))