from flask import Flask, jsonify, render_template, g, request
from datetime import datetime, timezone
from contextlib import contextmanager
from docker.errors import DockerException
import psycopg2
import docker
import logging
import time
import os


app = Flask(__name__)

APP_NAME = os.getenv("APP_NAME", "Network Monitoring Demo")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "app-db"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "network_monitor"),
    "user": os.getenv("DB_USER", "monitor_user"),
    "password": os.getenv(
        "DB_PASSWORD",
        "monitor_dev_password_change_me"
    ),
    "connect_timeout": 5,
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@contextmanager
def db_connection():
    connection = psycopg2.connect(**DB_CONFIG)

    try:
        yield connection
    finally:
        connection.close()


def init_db():
    for attempt in range(30):
        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS requests (
                            id BIGSERIAL PRIMARY KEY,
                            endpoint TEXT NOT NULL,
                            duration_ms DOUBLE PRECISION NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL
                        )
                    """)
                connection.commit()

            logger.info("PostgreSQL table is ready.")
            return

        except psycopg2.Error as error:
            logger.warning(
                "PostgreSQL is not ready (attempt %s/30): %s",
                attempt + 1,
                error
            )

            if attempt == 29:
                raise

            time.sleep(2)


def record_request(endpoint, duration_ms):
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO requests (
                        endpoint,
                        duration_ms,
                        created_at
                    )
                    VALUES (%s, %s, %s)
                    """,
                    (
                        endpoint,
                        duration_ms,
                        datetime.now(timezone.utc)
                    )
                )
            connection.commit()

    except psycopg2.Error:
        logger.exception("Could not save request statistics.")


def get_stats():
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    COUNT(*),
                    COALESCE(AVG(duration_ms), 0)
                FROM requests
            """)

            total, average = cursor.fetchone()

    return {
        "total_requests": total,
        "average_response_ms": round(float(average), 2)
    }


def check_database():
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone()[0] == 1


def get_container_ports(container):
    port_data = (
        container.attrs
        .get("NetworkSettings", {})
        .get("Ports")
        or {}
    )

    result = []

    for container_port, bindings in port_data.items():
        if bindings:
            for binding in bindings:
                host_ip = binding.get("HostIp", "0.0.0.0")
                host_port = binding.get("HostPort", "?")
                result.append(
                    f"{host_ip}:{host_port} -> {container_port}"
                )
        else:
            result.append(
                f"{container_port} (внутрішній порт)"
            )

    if not result:
        result.append("Немає опублікованих портів") 

    return result


def get_containers():
    client = docker.from_env(timeout=5)

    try:
        containers = client.containers.list(all=True)
        result = []

        for container in containers:
            container.reload()

            image_tags = container.image.tags
            image_name = (
                image_tags[0]
                if image_tags
                else container.attrs.get("Config", {}).get(
                    "Image", "unknown"
                )
            )

            result.append({
                "id": container.short_id,
                "name": container.name,
                "image": image_name,
                "status": container.status,
                "ports": get_container_ports(container)
            })

        result.sort(key=lambda item: item["name"].lower())
        return result

    finally:
        client.close()


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
    database_available = True

    try:
        stats = get_stats()
    except psycopg2.Error:
        logger.exception("Could not read statistics from PostgreSQL.")
        stats = {
            "total_requests": 0,
            "average_response_ms": 0
        }
        database_available = False

    return render_template(
        "index.html",
        app_name=APP_NAME,
        stats=stats,
        database_available=database_available
    )


@app.route("/health")
def health():
    try:
        check_database()

        return jsonify({
            "status": "healthy",
            "service": APP_NAME,
            "database": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200

    except psycopg2.Error:
        logger.exception("Health check failed: PostgreSQL unavailable.")

        return jsonify({
            "status": "unhealthy",
            "service": APP_NAME,
            "database": "unavailable",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 503


@app.route("/metrics")
def metrics():
    try:
        stats = get_stats()
    except psycopg2.Error:
        return jsonify({
            "error": "PostgreSQL is unavailable"
        }), 503

    body = "\n".join([
        f"app_requests_total {stats['total_requests']}",
        f"app_average_response_ms {stats['average_response_ms']}",
    ]) + "\n"

    return app.response_class(body, mimetype="text/plain")


@app.route("/api/stats")
def api_stats():
    try:
        return jsonify(get_stats())
    except psycopg2.Error:
        logger.exception("Statistics API could not access PostgreSQL.")

        return jsonify({
            "error": "PostgreSQL is unavailable"
        }), 503


@app.route("/api/test-request")
def test_request():
    time.sleep(0.05)

    return jsonify({
        "message": "Test request completed",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.route("/api/containers")
def api_containers():
    try:
        containers = get_containers()
        return jsonify({
            "count": len(containers),
            "containers": containers,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except DockerException:
        logger.exception("Docker Engine API is unavailable.")

        return jsonify({
            "error": "Docker Engine is unavailable",
            "details": (
                "Check Docker Desktop, Docker socket "
                "and container permissions."
            )
        }), 503

    except Exception:
        logger.exception("Could not retrieve Docker containers.")

        return jsonify({
            "error": "Could not retrieve container information"
        }), 500


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)