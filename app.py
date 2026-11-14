from flask import Flask, jsonify, render_template, request

import allergy
import engine

app = Flask(__name__)


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/analyze")
def api_analyze():
    try:
        return jsonify(allergy.analyze(request.get_json(force=True) or {}))
    except Exception:
        app.logger.exception("analyze failed")
        return jsonify({"error": "Something went wrong. Try again in a minute."}), 503


@app.get("/api/model")
def api_model():
    return jsonify(engine.RESULTS)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)