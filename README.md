# calender_sync

Google Calendar (ICS-Feed) → MariaDB Sync fürs Homelab.

Läuft als Docker Container, pollt periodisch einen privaten Google Calendar ICS-Feed, expandiert RRULE/EXDATE/RECURRENCE-ID und schreibt einzelne Instanzen in eine MariaDB-Datenbank.

## Features

- Automatische Synchronisation alle 15 Minuten (konfigurierbar)
- Expandiert wiederkehrende Events (RRULE) und Serien-Exceptions (EXDATE, RECURRENCE-ID)
- Soft-Delete: Entfernte Events werden als `deleted=1` markiert, nicht gelöscht
- Optionales Database-Bootstrap: Erstellt DB und User automatisch bei `DB_BOOTSTRAP=true`
- Zeitfenster-konfiguration für Vergangenheit/Future (standardmäßig -90 Tage / +365 Tage)
- Web-UI zur Anzeige anstehender Termine mit Suchfunktion
- REST API für programmsprachigen Zugriff auf Kalenderdaten
- Optionale tägliche E-Mail-Benachrichtigung um konfigurierte Uhrzeit

## Voraussetzungen

- Docker & Docker Compose
- MariaDB Instanz (z.B. als Proxmox LXC)
- Google Calendar mit privatem ICS-Feed

## Quick Start

1. **MariaDB Setup**

   Entweder manuell ausführen:
   ```bash
   mysql -u root -p < mariadb-setup.sql
   ```

   Oder automatisch beim Start (in `.env` setzen):
   ```
   DB_BOOTSTRAP=true
   DB_ROOT_USER=root
   DB_ROOT_PASSWORD=dein_root_passwort
   ```

2. **.env anlegen**

   ```bash
   cp .env.example .env
   ```

   Variablen anpassen, insbesondere:
   - `ICS_URL`: Privater ICS-Link aus den Google Calendar Einstellungen
   - `DB_PASSWORD`: Sicheres Passwort für den calendar_sync User

3. **Starten**

   ```bash
   docker compose up -d
   ```

## Konfiguration

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `ICS_URL` | *required* | Privater ICS-Feed aus Google Calendar |
| `CALENDAR_LABEL` | `default` | Label für den Kalender (für Multi-Kalender) |
| `DB_HOST` | `mariadb.fritz.box` | MariaDB Host |
| `DB_PORT` | `3306` | MariaDB Port |
| `DB_NAME` | `calendar_sync` | Datenbank-Name |
| `DB_USER` | *required* | Datenbank-User |
| `DB_PASSWORD` | *required* | Datenbank-Passwort |
| `SYNC_INTERVAL_MINUTES` | `15` | Sync-Intervall in Minuten |
| `WINDOW_PAST_DAYS` | `90` | Wie viele Tage in die Vergangenheit synchronisieren |
| `WINDOW_FUTURE_DAYS` | `365` | Wie viele Tage in die Zukunft synchronisieren |
| `LOG_LEVEL` | `INFO` | Python Logging Level |
| `DB_BOOTSTRAP` | `false` | DB + User beim Start erstellen |
| `DB_ROOT_USER` | - | Root-User fürs Bootstrap |
| `DB_ROOT_PASSWORD` | - | Root-Passwort fürs Bootstrap |
| `API_PORT` | `8000` | Port für den API/Web-UI Container |
| `TIMEZONE` | `UTC` | Zeitzone für API/Web-UI Anzeige (z.B. `Europe/Berlin`) |

### Optionale E-Mail-Benachrichtigung

Sendet täglich eine HTML-Email mit den anstehenden Terminen. Wird aktiviert wenn `SMTP_HOST` und `NOTIFY_EMAIL` gesetzt sind.

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `SMTP_HOST` | - | SMTP Server Hostname |
| `SMTP_PORT` | `587` | SMTP Server Port |
| `SMTP_USER` | - | SMTP Login Username |
| `SMTP_PASSWORD` | - | SMTP Login Passwort |
| `SMTP_FROM` | - | Absender E-Mail Adresse |
| `SMTP_USE_TLS` | `true` | TLS verschlüsselung nutzen |
| `NOTIFY_EMAIL` | - | Empfänger E-Mail Adresse |
| `NOTIFY_TIME` | `6` | Uhrzeit für Benachrichtigung (Stunde, 0-23) |
| `NOTIFY_TIMEZONE` | `Europe/Berlin` | Zeitzone für die Benachrichtigung |

**Subject-Logik:**
- 1 Termin: `Kalender heute: 09:00 - Meeting mit Team`
- 2+ Termine: `Kalender heute: 3 Termine`

**Hinweis:** Ganztagstermine werden nicht in der Benachrichtigung berücksichtigt.

## Datenbank-Schema

Tabelle `calendar_events`:

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `id` | BIGINT PK | Auto-Increment |
| `calendar_label` | VARCHAR(64) | Kalender-Label |
| `instance_key` | VARCHAR(255) | SHA1-basierte eindeutige Instanz-ID |
| `uid` | VARCHAR(255) | ICS UID |
| `recurrence_id` | VARCHAR(64) | RECURRENCE-ID bei Serien-Exceptions |
| `summary` | VARCHAR(512) | Titel |
| `description` | TEXT | Beschreibung |
| `location` | VARCHAR(512) | Ort |
| `start_at` | DATETIME | Startzeit (UTC) |
| `end_at` | DATETIME | Endzeit (UTC) |
| `all_day` | TINYINT(1) | Ganz-tagig Flag |
| `status` | VARCHAR(32) | Event-Status |
| `deleted` | TINYINT(1) | Soft-Delete Flag |
| `last_seen_at` | DATETIME | Letzte Synchronisation |
| `created_at` | DATETIME | Erstellungszeitpunkt |
| `updated_at` | DATETIME | Letzte Änderung |

Tabelle `daily_notification_log` (optional, für E-Mail-Benachrichtigung):

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `id` | INT PK | Auto-Increment |
| `notify_date` | DATE | Datum der Benachrichtigung |
| `sent_at` | DATETIME | Zeitpunkt des Versands |
| `event_count` | INT | Anzahl Termine in der Email |

## Web-UI & API

Das Projekt enthält eine FastAPI-basierte Webanwendung die als separater Container (`calendar-api`) läuft und auf Port `8000` erreichbar ist.

### Endpoints

| Endpoint | Beschreibung |
|----------|--------------|
| `GET /` | HTML-Seite mit anstehenden Terminen und Suchfunktion |
| `GET /api/health` | Health Check (gibt `{"status": "ok"}` zurück) |
| `GET /api/events?limit=10&search=...` | JSON-Liste zukünftiger Events (nicht gelöscht) |
| `GET /api/events/{event_id}` | Einzelnes Event als JSON |

### API Beispiel

```bash
# Alle anstehenden Events (max. 10)
curl http://localhost:8000/api/events

# Suche nach Titel
curl "http://localhost:8000/api/events?search=Meeting&limit=5"

# Einzelnes Event
curl http://localhost:8000/api/events/42
```

### JSON Response Format

```json
{
  "events": [
    {
      "id": 1,
      "summary": "Teammeeting",
      "description": "Wöchentliches Teammeeting",
      "location": "Konferenzraum 1",
      "start_at": "2025-01-15T10:00:00",
      "end_at": "2025-01-15T11:00:00",
       "all_day": false,
       "status": "CONFIRMED",
       "timezone": "Europe/Berlin"
     }
  ],
  "count": 1,
  "query_time": "2025-01-15T09:30:00Z",
  "timezone": "Europe/Berlin"
}
```

## CI/CD

GitHub Actions Workflow (`docker-publish.yml`) baut und published das Docker Image automatisch nach GitHub Container Registry:

```
ghcr.io/skoelle/calender_sync:latest
```

## Lizenz

Lizenziert unter der [MIT License](LICENSE) - Copyright (c) 2026 Stefan Koelle (https://stefankoelle.de)
