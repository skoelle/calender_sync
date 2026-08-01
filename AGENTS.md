# AGENTS.md

Richtlinien für AI-Agenten die mit dem calender_sync Projekt arbeiten.

## Projektübersicht

Python-basierter Google Calendar → MariaDB Synchronizer. Läuft als Docker Container im Homelab und pollt periodisch einen ICS-Feed.

## Technologie-Stack

- **Sprache**: Python 3.12
- **Datenbank**: MariaDB (mysql-connector-python)
- **Docker**: Multi-Stage Build nicht verwendet, simples Slim-Image
- **Dependencies**: requests, icalendar, recurring-ical-events, mysql-connector-python

## Projektstruktur

```
.
├── sync.py              # Hauptskript (alles in einer Datei)
├── requirements.txt     # Python Dependencies
├── Dockerfile           # Docker Image Definition
├── docker-compose.yml   # Docker Compose Konfiguration
├── mariadb-setup.sql    # Manuelles DB-Setup Script
├── .env.example         # Beispiel-Umgebungsvariablen
└── .github/workflows/   # CI/CD (Docker Build + Push)
```

## Wichtige Hinweise

### Kein Framework
Das Projekt verwendet kein Web-Framework. `sync.py` ist ein eigenständiges Python-Skript mit einer Endlosschleife (`main()` → `time.sleep()`).

### Datenbank-Schema
Schema wird in `ensure_schema()` per `CREATE TABLE IF NOT EXISTS` erstellt. Bei Schema-Änderungen:
- `ensure_schema()` in `sync.py:91` anpassen
- MariaDB-kompatibles SQL verwenden (kein PostgreSQL-Specific)
- Indexe für Performance bedenken

### Event-Expansion
Verwendet `recurring_ical_events` Bibliothek für RRULE/EXDATE/RECURRENCE-ID Expansion. Fenster wird über `WINDOW_PAST_DAYS`/`WINDOW_FUTURE_DAYS` gesteuert.

### UTC-Normalisierung
Alle Zeiten werden in naive UTC datetime konvertiert (`to_naive_utc()`). Bei Datumsänderungen sicherstellen, dass Zeitzone korrekt处理 wird.

### Soft-Delete
Events werden nicht gelöscht, sondern mit `deleted=1` markiert (`mark_missing_as_deleted()`).

## Entwicklung

### Lokaler Test
```bash
# Dependencies installieren
pip install -r requirements.txt

# .env anlegen (aus .env.example kopieren)
cp .env.example .env

# Direkt ausführen
python sync.py
```

### Linting & Type Checking
Keine Linting/Type-Checking Tools konfiguriert. Bei Bedarf hinzufügen:
- `ruff` für Linting
- `mypy` für Type Checking

### Tests
Keine Tests vorhanden. Bei Bedarf:
- `pytest` als Test-Framework verwenden
- Mock für `requests.get()` und `mysql.connector` erstellen
- Unit Tests für `to_naive_utc()`, `instance_key_for()`, `expand_events()`

## Code-Style

- Kein Docstring-Standard definiert
- Logging über `logging` Modul mit configurable Level
- Error Handling: Exceptions fangen, loggen, aber nicht verschlucken
- Keine externen Config-Libraries (nur `os.environ`)

## Docker

- Image basiert auf `python:3.12-slim`
- Kein Multi-Stage Build nötig (einfaches Projekt)
- `PYTHONUNBUFFERED=1` für Logging im Container
- Watchtower Label für Auto-Updates

## CI/CD

GitHub Actions Workflow:
- Baut Docker Image bei Push zu `main`
- Published nach `ghcr.io/skoelle/calender_sync:latest`
- Keine Tests im Workflow (derzeit)
