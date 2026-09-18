from flask import Flask, jsonify, render_template, g, request
from pathlib import Path
from datetime import datetime, timezone
import sqlite3
import time
import os

app = Flask(__name__)
DB_PATH = Path("/data/metrics.db")
APP_NAME = os.getenv("APP_NAME", "Network Monitoring Demo")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        connection.commit()


def record_request(endpoint, duration_ms):
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "INSERT INTO requests(endpoint, duration_ms, created_at) VALUES (?, ?, ?)",
            (endpoint, duration_ms, datetime.now(timezone.utc).isoformat())
        )
        connection.commit()


def get_stats():
    with sqlite3.connect(DB_PATH) as connection:
        total = connection.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        average = connection.execute(
            "SELECT COALESCE(AVG(duration_ms), 0) FROM requests"
        ).fetchone()[0]
    return {
        "total_requests": total,
        "average_response_ms": round(average, 2)
    }


@app.before_request
def start_timer():
    g.started_at = time.perf_counter()


@app.after_request
def finish_timer(response):
    started = getattr(g, "started_at", None)
    if started is not None and request.path != "/static/style.css":
        duration_ms = (time.perf_counter() - started) * 1000
        record_request(request.path, duration_ms)
    return response


@app.route("/")
def index():
    return render_template("index.html", app_name=APP_NAME, stats=get_stats())


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": APP_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.route("/metrics")
def metrics():
    stats = get_stats()
    body = "\n".join([
        "# HELP app_requests_total Total number of recorded requests",
        "# TYPE app_requests_total counter",
        f"app_requests_total {stats['total_requests']}",
        "# HELP app_average_response_ms Average response time in milliseconds",
        "# TYPE app_average_response_ms gauge",
        f"app_average_response_ms {stats['average_response_ms']}",
    ]) + "\n"
    return app.response_class(body, mimetype="text/plain")


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/test-request")
def test_request():
    time.sleep(0.05)
    return jsonify({
        "message": "Test request completed",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
