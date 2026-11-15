# AllerGuard AI 🌬️
**Personal allergy check and next-day air-quality planner for JLT, Dubai**

**Track:** Health  
**Team:** [Name 1], [Name 2]  
**Live site:** https://z76k.github.io/Hackathon-Project/

> **Main takeaway:** In one minute, a teenager with allergies gets AI-suggested triggers, a first-aid plan based on their answers, and the hours tomorrow when the air is safer *for them*.

## The problem
Many teenagers in Dubai have allergy symptoms like sneezing, coughing and itchy eyes, but don't know what sets them off, what to do first, or when a reaction becomes an emergency. Dust and fine particles (PM2.5) are common in JLT, and a level that's fine for one person can be too high for a teenager who coughs on dusty days. Our user is **a teen in JLT deciding the evening before when it's safe to go outside**.

## What we built
A website that works on phones and laptops.
- **In:** 5 quick questions (age group, symptoms, severity, what sets symptoms off, where they happen).
- **Out:**
  - **Possible triggers** with a reason for each, rated *Likely* or *Possible* (not a diagnosis)
  - **Tips and home remedies** matched to the person's symptoms and triggers
  - **A personal first-aid plan**, ending with when to call **998**
  - **Tomorrow's PM2.5 forecast for JLT**, the person's own limit, and **lower-risk hours** to be outside
- A first-aid guide for mild reactions, anaphylaxis and asthma attacks. Answers are never saved.

## What we added
We started from the suggested **"Next-day air quality forecast"** and added:
1. **Our own user and place.** The site is built for teenagers with allergies in JLT, Dubai, not a whole city.
2. **Personal limits.** The warning level is 35.4 µg/m³ (US EPA "sensitive groups") or 55.4 µg/m³ ("everyone"), depending on age, symptoms, severity and dust sensitivity, and the site explains *why*.
3. **Hour-by-hour lower-risk windows** for tomorrow, using PM2.5, feels-like temperature and UV.
4. **AI allergy analysis.** A language model turns the answers into triggers, tips, remedies and a first-aid plan, with a rule-based backup.
5. **A forecast that updates itself.** A GitHub Action retrains the model and publishes a new forecast every morning at 6 AM Dubai time.

## How it works
**Data.** Open-Meteo's air-quality (CAMS) and historical weather APIs for JLT (25.07° N, 55.14° E). We turned hourly readings into daily values: **1,405 days** in total, **1,090 for training (2023–2025)** and **315 for testing (2026)**.

**Forecast model.** A scikit-learn **Random Forest** predicts tomorrow's average PM2.5 from today's PM2.5 and weather. We chose it because it handles non-linear weather effects and works well on small tabular data. The 2026 test days were never used in training.

**AI analysis.** The 5 answers go to **Gemini 3.5 Flash-Lite**, with **Gemma 4** as a fallback. The prompt asks for JSON only, with no medicines or doses, dust mentioned only if the user chose it, and the last first-aid step always pointing to 998. Our code checks the reply and adds the emergency step if it's missing. If no model replies within 20 seconds, rules give the result instead, and the page labels which one was used.

## Results (315 test days from 2026, never seen in training)
| Method | Mean error (MAE) |
|---|---|
| Baseline: "tomorrow = today" | **8.5 µg/m³** |
| Our Random Forest | **9.0 µg/m³** |

**Honest result:** our model is **0.5 µg/m³ worse** than the simple baseline. PM2.5 in JLT changes slowly from day to day, so "tomorrow = today" is already a strong guess, and our weather features didn't add enough information to beat it. We kept the model because it is the base for the improvements below, and we report the baseline openly so users and judges can compare.

**Where it fails:**
- **Sudden dust events.** Dust blown in from elsewhere isn't visible in today's local readings, so both methods miss sudden spikes.
- **Location detail.** CAMS values are model estimates on a ~45 km grid, not street-level measurements.
- **The allergy analysis** suggests possibilities only. We haven't tested it against real diagnoses.

## What we'd do next
1. Add regional dust and wind-direction features so the model can see dust storms coming, the main reason it doesn't beat the baseline yet.
2. Test with real users with permission, and have a doctor review the first-aid content.

## Sources
- Open-Meteo Air Quality, Forecast and Historical Weather APIs: https://open-meteo.com
- Copernicus Atmosphere Monitoring Service (CAMS): https://atmosphere.copernicus.eu
- US EPA AQI for PM2.5: https://www.airnow.gov/aqi/aqi-basics/
- NWS heat index: https://www.weather.gov/safety/heat-index
- WHO UV index: https://www.who.int/news-room/questions-and-answers/item/radiation-the-ultraviolet-(uv)-index
- UAE emergency numbers: 998 (ambulance), 999 (police)
- Libraries: scikit-learn, pandas, Flask, google-genai
- AI model in the app: Google Gemini API (Gemini 3.5 Flash-Lite, Gemma 4)
- AI tools used while building: ChatGPT, Claude (in the Dia browser), Gemini

## Run it locally
    git clone https://github.com/z76k/Hackathon-Project && cd Hackathon-Project
    python -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    echo "GEMINI_API_KEY=your_key" > .env
    python app.py   # open http://localhost:5050

**This project is a prototype and is not medical advice.**


**Demo video (2 min):**

[![▶ Watch the AllerGuard AI demo](https://drive.google.com/thumbnail?id=1hIIq8_NR7MfnD1UmaX3Nmg52sSaehRBf&sz=w1000)](https://drive.google.com/file/d/1hIIq8_NR7MfnD1UmaX3Nmg52sSaehRBf/view?usp=sharing)