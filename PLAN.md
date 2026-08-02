# PLAN.md - Implementierungsplan

Feature: REST API + Web-Frontend für Calendar Sync

## Übersicht

Ziel: FastAPI-basierte API und ein Jinja2 Web-Frontend hinzufügen, um die nächsten 10 Termine aus MariaDB auszulesen und anzuzeigen. Gleicher Docker Build, separater Container.

---

## Phase 1: Projektstruktur + Shared Module

### Step 1.1: API-Verzeichnisstruktur anlegen
```
api/
├── __init__.py
├── main.py
├── database.py
└── templates/
    └── index.html
```

### Step 1.2: database.py - DB Connection extrahieren
- `get_connection()` Funktion aus `sync.py:81-89` in `api/database.py` verschieben
- Connection Pooling optional (First: einfacher single connection)
- Umgebungsvariablen identisch zu sync.py
- sync.py importiert dann `from api.database import get_connection`

**Dateien:** `api/__init__.py`, `api/database.py`, `sync.py` (Import anpassen)

---

## Phase 2: FastAPI Backend

### Step 2.1: api/main.py - FastAPI App erstellen
- FastAPI Instanz erstellen
- GET `/api/events` Endpoint
  - Query Parameter: `limit` (default 10, max 50), `calendar_label` (optional), `search` (optional)
  - SQL bei search: `WHERE deleted=0 AND start_at >= NOW() AND summary LIKE %s ORDER BY start_at ASC LIMIT %s`
  - SQL ohne search: `WHERE deleted=0 AND start_at >= NOW() ORDER BY start_at ASC LIMIT %s`
  - Response als JSON
- GET `/api/events/{id}` Endpoint
  - Einzelnes Event nach ID
- GET `/api/health` Endpoint
  - Response: `{"status": "ok"}`
- GET `/` Endpoint
  - Jinja2 Template rendern mit Events
  - Query Parameter `search` weiterleiten

### Step 2.2: Response Model definieren
- Pydantic Model für Event Response
- DATETIME → String Konvertierung (ISO Format)

**Dateien:** `api/main.py`

---

## Phase 3: Web-Frontend

### Step 3.1: api/templates/index.html
- Einfaches HTML5 Template
- Jinja2 Variablen: `{{ events }}`, `{{ search }}`
- CSS inline oder im `<style>` Block
- Suchfeld oben (Formular mit GET Parameter `search`)
- Darstellung:
  - Datum + Uhrzeit (oder "Ganztägig")
  - Titel (summary)
  - Ort (location) - falls vorhanden
  - Status Badge (grün=CONFIRMED, gelb=TENTATIVE, rot=CANCELLED)
- Kein JavaScript nötig (nur server-side rendering)

**Dateien:** `api/templates/index.html`

---

## Phase 4: Dependencies + Docker

### Step 4.1: requirements.txt erweitern
```
fastapi==0.115.0
uvicorn[standard]==0.30.0
jinja2==3.1.4
```

### Step 4.2: Dockerfile anpassen
- `COPY api/ ./api/` hinzufügen
- Standard CMD bleibt `python sync.py`

### Step 4.3: docker-compose.yml erweitern
- `calendar-api` Service hinzufügen
  - Gleicher Image
  - `command: ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]`
  - Port Mapping: `${API_PORT:-8000}:8000`
  - DB Environment Variablen
  - Watchtower Label

### Step 4.4: .env.example erweitern
- `API_PORT=8000` hinzufügen

**Dateien:** `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.env.example`

---

## Phase 5: Refactoring sync.py

### Step 5.1: sync.py importieren
- `from api.database import get_connection` verwenden
- Lokale `get_connection()` Funktion entfernen
- Database Bootstrap bleibt in sync.py (gehört nicht zur API)

---

## Zusammenfassung der zu erstellenden Dateien

| Datei                   | Aktion          |
|-------------------------|-----------------|
| `api/__init__.py`       | Neu erstellen   |
| `api/database.py`       | Neu erstellen   |
| `api/main.py`           | Neu erstellen   |
| `api/templates/index.html` | Neu erstellen |
| `sync.py`               | Import anpassen |
| `requirements.txt`      | Erweitern       |
| `Dockerfile`            | Erweitern       |
| `docker-compose.yml`    | Erweitern       |
| `.env.example`          | Erweitern       |

---

## Offene Punkte

- [x] Zeitzonen-Korrektur in API und Web-UI (statt GMT → lokaler Zeitzone)
- [x] Notwendigkeit eines timezone-Feldes in der DB für korrekte Speicherung
- [x] Zeitstempel-Speicherung mit korrekter Zeitzone-Feldunterstützung in DB
- [x] DB Bootstrap - bleibt in sync.py
- [x] Template Styling - einfaches CSS, kein Framework
- [x] Search - optionaler Suchbegriff auf Event-Titel (API + Frontend)

## Richtig gelöst: Keine DB-Zeitzone-Speicherung nötig

Da MySQL/MariaDB naive DATETIME-Werte speichert (ohne Zeitzone), muss die Zeitzone-Zuweisung auf der API/Web-UI-Seite erfolgen. Dies ist korrekt, da:

1. **Datenbank-Speicherung**: MariaDB DATETIME-Spalten können naive Datetimes speichern (alle in einem Standard)
2. **Zeitzone-Wiederherstellung**: Die API/Frontend-Komponenten können naive Datetimes in die korrekte Benutzer-Zeitzone konvertieren, wenn sie benötigt werden
3. **Vereinfachte Architektur**: Keine komplexe DB-Schema-Änderung erforderlich

**Lösung**: Konvertieren Sie naive UTC-Daten aus DB → lokale Zeitzone im API/Web-UI durch Hinzufügen von `timezone`-Feld in Response-Modell.

**Änderungen**:
- Fügen Sie ein `timezone`-Feld zu `EventResponse` und `EventsListResponse` hinzu
- Konvertieren Sie Datetimes in API: `datetime.now(timezone.utc)` → `to_local_timezone()`
- Passen Sie `row_to_event` an: Konvertieren Sie naive UTC → Benutzer-Zeitzone
- Aktualisieren Sie das Template: Verwenden Sie den Zeitzonennamen für Formatierung
