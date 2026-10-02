# Network Monitoring Web Application

## Flask + Nginx + PostgreSQL + Docker + Docker Compose + Zabbix + Wireshark

## Опис проєкту

**Network Monitoring Web Application** --- навчальний багатоконтейнерний
мережевий вебзастосунок, розроблений на Python із використанням Flask та
розгорнутий у Linux-середовищі WSL2 з Docker Engine і Docker Compose.

Кінцева архітектура: **клієнт → Nginx reverse proxy → Flask application
→ PostgreSQL**. Основні сервіси працюють у користувацькій Docker
bridge-мережі `monitoring_net` з адресним простором `172.28.0.0/24`.
Зовні опубліковано лише порт Nginx `8080`; Flask і PostgreSQL не мають
безпосередньо опублікованих портів хоста.

Система додатково містить Zabbix для моніторингу доступності Flask
та Wireshark для аналізу HTTP/TCP-трафіку і окремо запити до бази даних.

## Архітектура

``` text
Linux / WSL2
└── Docker Engine
    └── monitoring_net (bridge, 172.28.0.0/24)
        ├── proxy        → Nginx :80, host :8080
        ├── web          → Flask :5000, not published
        ├── app-db       → PostgreSQL :5432, not published
        ├── zabbix-server
        ├── zabbix-web
        ├── zabbix-db    → PostgreSQL :5432
        └── zabbix-agent → Zabbix Agent 2
```

Взаємодія:

``` text
Host → proxy:8080 → web:5000 → app-db:5432
Zabbix Server → web:5000/health
Zabbix Server → zabbix-db:5432
```

## Docker network

`monitoring_net` --- користувацька bridge-мережа: - Driver: `bridge` -
Subnet: `172.28.0.0/24` - Gateway: `172.28.0.1` - DNS: Docker embedded
DNS

Сервіси звертаються за іменами `web`, `app-db`, `zabbix-db`, а не за як таким
фіксованими IP.

## Docker та Docker Compose

Перевірка Docker:

``` bash
docker version
docker info
systemctl status docker --no-pager
docker context ls
docker context show
```

Перевірка Compose:

``` bash
docker compose version
docker compose config --quiet
docker compose ps
```

Запуск:

``` bash
docker compose up -d --build
```

Логи:

``` bash
docker compose logs --tail=100
```

Зупинка:

``` bash
docker compose stop
```

Повторний запуск:

``` bash
docker compose start
```

## Nginx reverse proxy

`proxy` використовує `nginx:1.27-alpine`. Він є єдиною зовнішньою точкою
входу до Flask.

``` text
Host :8080 → Nginx :80 → web:5000
```

Перевірка:

``` bash
docker port network-monitor-proxy
docker compose logs --tail=100 proxy
docker compose port web 5000
```

## Flask / Python

`web` --- Flask-застосунок на Python 3.12. Внутрішній порт --- `5000`.

Основні endpoint: - `/` --- головна сторінка; - `/health` --- перевірка
Flask і PostgreSQL; - `/api/stats` --- статистика HTTP; -
`/api/test-request` --- тестовий запит; - `/metrics` --- базові метрики.

Перевірка через Nginx:

``` bash
curl -i -H 'Host: monitor.local' http://127.0.0.1:8080/health
curl -i -H 'Host: monitor.local' http://127.0.0.1:8080/api/stats
curl -i -H 'Host: monitor.local' http://127.0.0.1:8080/api/test-request
```

`/health` є ключовим endpoint для Zabbix і перевіряє не лише Flask, а й
доступність PostgreSQL.

## PostgreSQL

`app-db` використовує PostgreSQL 16 і внутрішній порт `5432`. Дані
статистики зберігаються в таблиці `requests` з полями: - `id`; -
`endpoint`; - `duration_ms`; - `created_at`.

Перевірка:

``` bash
docker compose exec app-db pg_isready
docker compose exec app-db psql -U monitor_user -d network_monitor
```

Приклад SQL:

``` sql
SELECT id, endpoint, duration_ms, created_at
FROM requests
ORDER BY id DESC
LIMIT 10;
```

Окремо працює `zabbix-db`, яка зберігає службові дані Zabbix.

## Docker DNS

Перевірка:

``` bash
docker compose exec web cat /etc/resolv.conf
docker compose exec web python -c "import socket; print(socket.gethostbyname('app-db'))"
```

Docker DNS дозволяє Flask знаходити PostgreSQL за `app-db` без ручного
прописування IP.

## TCP/IP та мережеві перевірки

Перевірка Flask → PostgreSQL:

``` bash
docker compose exec web python -c "import socket; s=socket.create_connection(('app-db',5432),3); print('TCP PostgreSQL: OK'); s.close()"
```

Netshoot:

``` bash
docker run --rm --network monitoring_net nicolaka/netshoot ip addr
docker run --rm --network monitoring_net nicolaka/netshoot ip route
docker run --rm --network monitoring_net nicolaka/netshoot nc -vz -w 3 web 5000
docker run --rm --network monitoring_net nicolaka/netshoot nc -vz -w 3 app-db 5432
```

IP контейнерів:

``` bash
docker network inspect monitoring_net --format '{{range .Containers}}{{println .Name .IPv4Address}}{{end}}'
```

## Ізоляція

Flask і PostgreSQL не публікують свої порти на хост. Для перевірки:

``` bash
docker inspect network-monitor-web --format '{{(index .NetworkSettings.Networks "monitoring_net").IPAddress}}'
docker run --rm --network bridge nicolaka/netshoot getent hosts web
```

## Healthcheck

Стан healthcheck:

``` bash
docker inspect network-monitor-web --format '{{json .State.Health}}'
```

Healthcheck використовує `/health` і дозволяє Docker контролювати
готовність Flask.

## Zabbix

Zabbix складається з: - `zabbix-server`; - `zabbix-web`; -
`zabbix-db`; - `zabbix-agent`.

Логіка моніторингу:

``` text
Zabbix HTTP Agent
      ↓
GET /health
      ↓
Flask
      ↓
HTTP 200 / помилковий стан
      ↓
Item
      ↓
Trigger
      ↓
OK / PROBLEM
```

Для тесту:

``` bash
docker compose stop web
```

Відновлення:

``` bash
docker compose start web
```

## Wireshark

Wireshark використовується для аналізу HTTP трафіку та окремо запитів до бази даних застосунку .

Створення трафіку HTTP:

``` bash
curl -i -H 'Host: monitor.local' http://127.0.0.1:8080/health
curl -i -H 'Host: monitor.local' http://127.0.0.1:8080/api/stats
```

Створення трафіку до бази даних вебдодатку:
``` bash
docker run --rm \
  --network container:network-monitor-web \
  --cap-add NET_ADMIN \
  --cap-add NET_RAW \
  -v "$PWD/captures:/captures" \
  nicolaka/netshoot \
  tcpdump -i any -nn -s0 -w /captures/postgres.pcap 'tcp port 5432'
```