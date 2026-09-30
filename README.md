# Network Monitoring Web Application (Flask + Docker + PostgreSQL + Zabbix + Wireshark)

## 📌 Опис проєкту

Вебзастосунок створено на Python із використанням Flask. Він призначений
для моніторингу доступності вебсервісу, збору статистики HTTP-запитів,
перегляду інформації про Docker-контейнери та дослідження мережевого
трафіку.

Система використовує Docker і Docker Compose для запуску
взаємопов'язаних компонентів. Статистика вебзастосунку зберігається в
окремій базі PostgreSQL, а Zabbix використовує власну базу PostgreSQL.

------------------------------------------------------------------------

## 🎯 Функціональні можливості

### 🌐 Вебзастосунок Flask

-   відображає головну сторінку з показниками роботи застосунку;
-   надає endpoint перевірки стану `/health`;
-   надає API статистики `/api/stats`;
-   надає тестовий endpoint `/api/test-request`;
-   реєструє HTTP-запити, вимірює тривалість обробки та обчислює
    середній час відповіді;
-   зберігає статистику в PostgreSQL;
-   надає endpoint `/metrics` для базових показників у текстовому
    форматі;
-   надає endpoint `/api/containers`, який через отримує
    назви, образи, стани та опубліковані порти контейнерів.

### 📊 Моніторинг Zabbix

-   запускає Zabbix Server і вебінтерфейс Zabbix у контейнерах;
-   використовує окрему базу PostgreSQL для службових даних Zabbix;
-   дає змогу налаштувати HTTP agent для перевірки `/health`;
-   дозволяє переглядати останні отримані значення та налаштовувати
    тригери;
-   допомагає виявляти ситуації, коли застосунок перестає відповідати.

### 🐳 Контейнеризація Docker

-   `web` --- Flask-застосунок;
-   `app-db` --- PostgreSQL для статистики HTTP-запитів;
-   `zabbix-server` --- сервер моніторингу;
-   `zabbix-web` --- вебінтерфейс Zabbix;
-   `zabbix-db` --- PostgreSQL для службових даних Zabbix;
-   `monitoring_net` --- користувацька bridge-мережа для взаємодії
    сервісів;
-   Docker volumes --- для збереження даних баз даних;
-   Docker SDK for Python (`docker-py`) --- для отримання інформації про
    контейнери через Docker API.

### 🦈 Аналіз мережевого трафіку Wireshark

-   дозволяє аналізувати HTTP-запити, відповіді та TCP-з'єднання;
-   може використовуватися для дослідження локального HTTP-трафіку;
-   дає змогу організувати окреме захоплення трафіку між Flask і
    PostgreSQL.

------------------------------------------------------------------------

## 🧱 Архітектура та бази даних

Проєкт використовує як такі **дві окремі бази PostgreSQL**.

### 1. PostgreSQL застосунку (`app-db`)

База зберігає статистику HTTP-запитів у таблиці `requests`:

-   `id` --- унікальний ідентифікатор запису;
-   `endpoint` --- endpoint, до якого надійшов запит;
-   `duration_ms` --- тривалість обробки в мілісекундах;
-   `created_at` --- дата й час створення запису.

Flask підключається до `app-db` за внутрішнім ім'ям сервісу та портом
PostgreSQL `5432`.

### 2. PostgreSQL Zabbix (`zabbix-db`)

Окрема база зберігає конфігурацію Zabbix, елементи даних, тригери та
історію показників.

### Взаємодія компонентів

-   браузер → Flask через порт `5000`;
-   Flask → `app-db` через внутрішню Docker-мережу;
-   Zabbix Server → `zabbix-db` через внутрішню Docker-мережу;
-   браузер → Zabbix Web через порт `8080`;
-   Flask → Docker API через змонтований Docker socket.

------------------------------------------------------------------------

## 🛠 Використані технології

-   Python 3.12;
-   Flask;
-   PostgreSQL для статистики вебзастосунку;
-   PostgreSQL для Zabbix;
-   SQL;
-   Docker;
-   Docker Compose;
-   Docker SDK for Python (`docker-py`);
-   Zabbix 7.0;
-   Wireshark;
-   HTTP, JSON і TCP/IP.

------------------------------------------------------------------------

## 🌐 Інтерфейс та API

HTML-сторінка формується Flask через шаблон `index.html`.

-   Flask Web Application: `http://localhost:5000`
-   Health Check: `http://localhost:5000/health`
-   API Statistics: `http://localhost:5000/api/stats`
-   Test Request: `http://localhost:5000/api/test-request`
-   Metrics: `http://localhost:5000/metrics`
-   Docker Containers: `http://localhost:5000/api/containers`
-   Zabbix Web Interface: `http://localhost:8080`

------------------------------------------------------------------------

## ▶️ Запуск проєкту

Запустити усі сервіси:

``` bash
docker compose up -d --build
```

Перевірити стан контейнерів:

``` bash
docker compose ps
```

Переглянути журнали:

``` bash
docker compose logs --tail=100
```

Перевірити основні endpoint:

``` bash
curl -i http://localhost:5000/health
curl -i http://localhost:5000/api/stats
curl -i http://localhost:5000/api/test-request
curl -i http://localhost:5000/api/containers
```

Переглянути останні записи в PostgreSQL застосунку:

``` bash
docker compose exec app-db psql -U monitor_user -d network_monitor \
  -c "SELECT id, endpoint, duration_ms, created_at FROM requests ORDER BY id DESC LIMIT 10;"
```

Зупинити контейнери без видалення:

``` bash
docker compose stop
```

Повторно запустити зупинені контейнери:

``` bash
docker compose start
```

Зупинити й видалити контейнери та мережі Compose:

``` bash
docker compose down
```

------------------------------------------------------------------------

## 🧪 Перевірка мережевого трафіку

Для HTTP-трафіку у Wireshark можна застосувати фільтр:

``` text
tcp.port == 5000
```

Для PostgreSQL-з'єднань:

``` text
tcp.port == 5432
```

Другий фільтр показує пакети лише тоді, коли захоплення відбувається на
інтерфейсі, через який проходить внутрішній трафік Docker. Щоб отримати
такий трафік, може знадобитися `tcpdump` у діагностичному контейнері,
під'єднаному до мережевого простору контейнера `web`. Під час захоплення
потрібно створити запити до `/health` або `/api/stats`, а потім відкрити
збережений файл у Wireshark.
