from datetime import datetime, timezone
import os
import time

import docker
import psycopg2
from flask import Flask, g, jsonify, render_template, request


app = Flask(__name__)

APP_NAME = os.getenv("APP_NAME", "Network Monitoring Demo")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "app-db"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "network_monitor"),
    "user": os.getenv("DB_USER", "monitor_user"),
    "password": os.getenv("DB_PASSWORD", ""),
    "connect_timeout": 3,
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id BIGSERIAL PRIMARY KEY,
                    endpoint TEXT NOT NULL,
                    duration_ms DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
            """)


def record_request(endpoint, duration_ms):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO requests (endpoint, duration_ms, created_at)
                VALUES (%s, %s, %s)
                """,
                (
                    endpoint,
                    duration_ms,
                    datetime.now(timezone.utc),
                ),
            )


def get_stats():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    COUNT(*),
                    COALESCE(AVG(duration_ms), 0)
                FROM requests
            """)
            total, average = cursor.fetchone()

    return {
        "total_requests": int(total),
        "average_response_ms": round(float(average), 2),
    }


@app.before_request
def start_timer():
    g.started_at = time.perf_counter()


@app.after_request
def finish_timer(response):
    started = getattr(g, "started_at", None)

    if started is not None and not request.path.startswith("/static/"):
        duration_ms = (time.perf_counter() - started) * 1000

        try:
            record_request(request.path, duration_ms)
        except Exception:
            app.logger.exception("Failed to record request in PostgreSQL")

    return response

@app.route("/api/containers")
def api_containers():
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True)

        result = []

        for container in containers:
            ports = []

            container_ports = (
                container.attrs.get("NetworkSettings", {}).get("Ports", {})
                or {}
            )

            for container_port, bindings in container_ports.items():
                if bindings:
                    for binding in bindings:
                        host_ip = binding.get("HostIp", "")
                        host_port = binding.get("HostPort", "")

                        if host_ip in ("", "0.0.0.0", "::"):
                            ports.append(
                                f"{host_port}->{container_port}"
                            )
                        else:
                            ports.append(
                                f"{host_ip}:{host_port}->{container_port}"
                            )
                else:
                    ports.append(container_port)

            result.append({
                "id": container.short_id,
                "name": container.name,
                "image": (
                    container.image.tags[0]
                    if container.image.tags
                    else container.image.short_id
                ),
                "status": container.status,
                "ports": ports,
            })

        client.close()

        return jsonify({
            "count": len(result),
            "containers": result,
        })

    except Exception:
        app.logger.exception("Failed to get Docker containers")

        return jsonify({
            "count": 0,
            "containers": [],
            "error": "Docker API unavailable",
        }), 503

@app.route("/")
def index():
    database_available = True

    try:
        stats = get_stats()
    except Exception:
        app.logger.exception("Failed to load PostgreSQL statistics")
        stats = {
            "total_requests": 0,
            "average_response_ms": 0,
        }
        database_available = False

    return render_template(
        "index.html",
        app_name=APP_NAME,
        stats=stats,
        database_available=database_available,
    )


@app.route("/health")
def health():
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")

        return jsonify({
            "status": "healthy",
            "service": APP_NAME,
            "database": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 200

    except Exception:
        app.logger.exception("Health check failed")

        return jsonify({
            "status": "unhealthy",
            "database": "unavailable",
        }), 503


@app.route("/metrics")
def metrics():
    stats = get_stats()

    body = "\n".join([
        f"app_requests_total {stats['total_requests']}",
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)