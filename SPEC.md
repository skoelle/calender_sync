# SPEC.md - Calendar Sync Projekt

## 1. Projektübersicht

Python-basiertes System zur Synchronisation eines Google Calendar ICS-Feeds nach MariaDB, mit zusätzlichem REST API + Web-Frontend für die Anzeige der nächsten Termine. Läuft als Docker Container im Homelab.

## 2. Architektur

```
┌─────────────────────┐      ┌─────────────────────┐
│   calendar-sync     │      │   calendar-api      │
│   (Sync Tool)       │      │   (FastAPI + HTML)  │
│                     │      │                     │
│  - ICS Polling      │      │  - REST API         │
│  - RRULE Expansion  │      │  - Web-Frontend     │
│  - MariaDB Write    │      │  - MariaDB Read     │
└──────────┬──────────┘      └──────────┬──────────┘
           │                            │
           └────────────┬───────────────┘
                        │
               ┌────────▼────────┐
               │     MariaDB     │
               │  calendar_sync  │
               └─────────────────┘
```

**Entscheidung:** Gleicher Docker Build (ein Dockerfile), zwei verschiedene Container/Services via `docker-compose.yml`. Der jeweilige Service wird via `command` Parameter gesteuert (`python sync.py` vs. `uvicorn api.main:app`).

## 3. Bestehendes System (Sync Tool)

### 3.1 Funktionen
- Lädt periodisch einen ICS-Feed von Google Calendar
- Expandiert wiederkehrende Events (RRULE/EXDATE/RECURRENCE-ID)
- Schreibt Einzel-Instanzen in MariaDB (calendar_events Tabelle)
- Soft-Delete: Events werden mit `deleted=1` markiert statt gelöscht
- Optionaler Healthcheck-Ping nach jedem Sync-Durchlauf
- Optionale Datenbank-Bootstrap (DB + User anlegen)

### 3.2 Datenbank-Schema (calendar_events)
| Feld              | Typ                  | Beschreibung                    |
|-------------------|----------------------|----------------------------------|
| id                | BIGINT AUTO_INCREMENT| Primärschlüssel                 |
| calendar_label    | VARCHAR(64)          | Kalender-Bezeichnung             |
| instance_key      | VARCHAR(255)         | SHA1 Hash (UID + RECURRENCE-ID) |
| uid               | VARCHAR(255)         | Originale Event UID              |
| recurrence_id     | VARCHAR(64)          | RECURRENCE-ID (nullable)         |
| summary           | VARCHAR(512)         | Titel des Events                 |
| description       | TEXT                 | Beschreibung                     |
| location          | VARCHAR(512)         | Ort                              |
| start_at          | DATETIME             | Startzeit (naive UTC)            |
| end_at            | DATETIME             | Endzeit (naive UTC, nullable)    |
| all_day           | TINYINT(1)           | Ganzägiges Event                 |
| status            | VARCHAR(32)          | CONFIRMED/CANCELLED/TENTATIVE    |
| deleted           | TINYINT(1)           | Soft-Delete Flag                 |
| last_seen_at      | DATETIME             | Letzter Sync-Zeitpunkt           |
| created_at        | DATETIME             | Erstellungszeitpunkt             |
| updated_at        | DATETIME             | Letzter Update-Zeitpunkt         |

### 3.3 Environment Variablen
- `ICS_URL` (required) - Google Calendar ICS Feed URL
- `CALENDAR_LABEL` - Bezeichnung für den Kalender
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` - MariaDB Zugangsdaten
- `SYNC_INTERVAL_MINUTES` - Sync Intervall (default: 15)
- `WINDOW_PAST_DAYS`, `WINDOW_FUTURE_DAYS` - Zeitfenster für Events
- `LOG_LEVEL` - Logging Level
- `HEALTHCHECK_URL` - Optionaler Healthcheck Endpoint
- `DB_BOOTSTRAP`, `DB_ROOT_USER`, `DB_ROOT_PASSWORD` - Optionales DB Bootstrap

## 4. Neues System (API + Web-Frontend)

### 4.1 REST API Endpoints

#### GET /api/events
Gibt die nächsten N Termine zurück.

**Query Parameter:**
- `limit` (optional, default: 10, max: 50) - Anzahl der Events
- `calendar_label` (optional) - Filter nach Kalender
- `search` (optional) - Suchbegriff für Event-Titel (LIKE %search%)

**Response (JSON):**
```json
{
  "events": [
    {
      "id": 123,
      "summary": "Meeting mit Team",
      "description": "...",
      "location": "Raum 101",
      "start_at": "2025-01-15T10:00:00",
      "end_at": "2025-01-15T11:00:00",
       "all_day": false,
       "status": "CONFIRMED",
       "timezone": "Europe/Berlin"
     }
   ],
  "count": 10,
  "query_time": "2025-01-14T14:30:00Z",
  "timezone": "Europe/Berlin"
}
```

#### GET /api/events/{id}
Gibt ein einzelnes Event zurück.

#### GET /api/health
Healthcheck Endpoint für den API Container.

### 4.2 Web-Frontend

**URL:** `http://localhost:8000/` (oder konfigurierbarer Port)

**Funktionen:**
- Zeigt die nächsten 10 Termine in einer übersichtlichen Liste
- Suchfeld oben (optional, filtert nach Event-Titel)
- Responsive Design (funktioniert auf Desktop und Handy)
- Einfaches, cleanes Design ohne Framework (nur HTML + CSS + vanilla JS)

**Darstellung pro Event:**
- Datum + Uhrzeit (oder "Ganztägig")
- Titel (summary)
- Ort (location) - falls vorhanden
- Status-Anzeige (Farbcode: grün=CONFIRMED, gelb=TENTATIVE, rot=CANCELLED)

### 4.3 Technologie-Stack (API)
- **Framework:** FastAPI
- **Templating:** Jinja2 (server-side rendering)
- **DB-Zugriff:** mysql-connector-python (shared `get_connection()` aus `api/database.py`)
- **Port:** 8000 (konfigurierbar via `API_PORT`)

### 4.4 Additional Environment Variablen (API)
- `API_PORT` - Port für den API Server (default: 8000)
- `TIMEZONE` - Zeitzone für die Anzeige von Zeiten (default: UTC)
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` - Identisch zum Sync

## 5. Docker Setup

### 5.1 Dockerfile (erweitert)
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sync.py .
COPY api/ ./api/

ENV PYTHONUNBUFFERED=1

# Default: Sync Tool
CMD ["python", "sync.py"]
```

Das Image enthält sowohl das Sync-Tool als auch die API. Der jeweilige Service wird via `docker-compose.yml` gesteuert.

### 5.2 Docker Compose (erweitert)
```yaml
services:
  calendar-sync:
    image: ghcr.io/skoelle/calender_sync:latest
    container_name: calendar-sync
    restart: unless-stopped
    command: ["python", "sync.py"]
    environment:
      - ICS_URL=${ICS_URL}
      - CALENDAR_LABEL=${CALENDAR_LABEL:-privat}
      - DB_HOST=${DB_HOST:-mariadb.fritz.box}
      - DB_PORT=${DB_PORT:-3306}
      - DB_NAME=${DB_NAME:-calendar_sync}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - SYNC_INTERVAL_MINUTES=${SYNC_INTERVAL_MINUTES:-15}
      - WINDOW_PAST_DAYS=${WINDOW_PAST_DAYS:-90}
      - WINDOW_FUTURE_DAYS=${WINDOW_FUTURE_DAYS:-365}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - HEALTHCHECK_URL=${HEALTHCHECK_URL:-}
      - DB_BOOTSTRAP=${DB_BOOTSTRAP:-false}
      - DB_ROOT_USER=${DB_ROOT_USER:-}
      - DB_ROOT_PASSWORD=${DB_ROOT_PASSWORD:-}
    networks:
      - docker-backend

  calendar-api:
    image: ghcr.io/skoelle/calender_sync:latest
    container_name: calendar-api
    restart: unless-stopped
    command: ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
    ports:
      - "${API_PORT:-8000}:8000"
    environment:
      - DB_HOST=${DB_HOST:-mariadb.fritz.box}
      - DB_PORT=${DB_PORT:-3306}
      - DB_NAME=${DB_NAME:-calendar_sync}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - TIMEZONE=${TIMEZONE:-UTC}
    labels:
      - "com.centurylinklabs.watchtower.enable=true"
    networks:
      - docker-backend

networks:
  docker-backend:
    external: true
```

## 6. Projektstruktur (Zielstruktur)

```
.
├── sync.py                 # Hauptskript Sync Tool
├── api/
│   ├── __init__.py
│   ├── main.py             # FastAPI App + Routes
│   ├── database.py         # DB Connection Pool (shared)
│   └── templates/
│       └── index.html      # Jinja2 Template für Web-Frontend
├── requirements.txt        # Python Dependencies (erweitert)
├── Dockerfile              # Docker Image Definition (erweitert)
├── docker-compose.yml      # Docker Compose Konfiguration (erweitert)
├── mariadb-setup.sql       # Manuelles DB-Setup Script
├── .env.example            # Beispiel-Umgebungsvariablen (erweitert)
├── SPEC.md                 # Diese Spezifikation
├── PLAN.md                 # Implementierungsplan
├── AGENTS.md               # Richtlinien für AI-Agenten
└── .github/workflows/      # CI/CD (Docker Build + Push)
```

## 7. Dependencies (requirements.txt)

```
requests==2.32.3
icalendar==6.1.0
recurring-ical-events==3.4.1
mysql-connector-python==9.1.0
fastapi==0.115.0
uvicorn[standard]==0.30.0
jinja2==3.1.4
```

## 8. Design-Entscheidungen

| Thema                  | Entscheidung                              |
|------------------------|-------------------------------------------|
| API Authentifizierung  | Keine (nur Homelab intern)                |
| Caching                | Kein (SQL Query bei jedem Request)        |
| Auto-Refresh Frontend  | Kein (manueller Reload)                   |
| CORS                   | Kein (Same-Origin via Jinja2 Templates)   |
| Multi-Sync             | Nicht benötigt                            |
| iCal Export            | Nicht benötigt                            |
| Benachrichtigungen     | Nicht benötigt                            |
| Dark Mode              | Nicht benötigt                            |
| Search                 | Optionaler Suchbegriff auf Event-Titel    |
| DB Bootstrap           | Bleibt in sync.py                         |
| Template Styling       | Einfaches CSS, kein Framework             |
| Logging                | Nur Errors + Request Log auf INFO Level   |

## 9. Testing

### 9.1 Unit Tests (optional, später)
- `test_to_naive_utc()` - Zeitkonvertierung
- `test_instance_key_for()` - Key Generation
- API Endpoint Tests mit `httpx` + `pytest`

### 9.2 Integration Tests (optional, später)
- Sync Tool → DB → API → Response validieren

## 10. CI/CD

Bestehender GitHub Actions Workflow erweitern:
- Build einmal für beide Services
- Optional: Separater Tag für API-only Image

## 11. Future Enhancements (nicht im Scope)

- [ ] Kalender-Filter UI (nach calendar_label)
- [x] Suchfunktion nach Event-Titel (implementiert)
