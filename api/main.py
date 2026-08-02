import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from api.database import get_connection

log = logging.getLogger("calendar-api")

app = FastAPI(title="Calendar Sync API")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

SELECT_COLUMNS = "id, summary, description, location, start_at, end_at, all_day, status"

# Get timezone from environment, default to UTC
TIMEZONE_NAME = os.environ.get("TIMEZONE", "UTC")
try:
    TIMEZONE = ZoneInfo(TIMEZONE_NAME)
except Exception:
    log.warning(f"Invalid TIMEZONE '{TIMEZONE_NAME}', falling back to UTC")
    TIMEZONE = ZoneInfo("UTC")


def to_local_timezone(dt: datetime) -> datetime:
    """Konvertiere naive UTC datetime zu Benutzer-Zeitzone."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(TIMEZONE)


def to_iso_local(dt: datetime) -> str:
    """Konvertiere naive UTC datetime zu ISO-String in lokaler Zeitzone."""
    if dt is None:
        return None
    local_dt = to_local_timezone(dt)
    return local_dt.isoformat()


class EventResponse(BaseModel):
    id: int
    summary: str | None
    description: str | None
    location: str | None
    start_at: str
    end_at: str | None
    timezone: str
    all_day: bool
    status: str


class EventsListResponse(BaseModel):
    events: list[EventResponse]
    count: int
    query_time: str
    timezone: str


def row_to_event(row) -> EventResponse:
    return EventResponse(
        id=row[0],
        summary=row[1],
        description=row[2],
        location=row[3],
        start_at=to_iso_local(row[4]) if row[4] else None,
        end_at=to_iso_local(row[5]) if row[5] else None,
        timezone=TIMEZONE_NAME,
        all_day=bool(row[6]),
        status=row[7],
    )


def fetch_events(limit: int = 10, search: str | None = None) -> list[dict]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            if search:
                cur.execute(
                    f"SELECT {SELECT_COLUMNS} FROM calendar_events "
                    "WHERE deleted = 0 AND start_at >= NOW() AND summary LIKE %s "
                    "ORDER BY start_at ASC LIMIT %s",
                    (f"%{search}%", limit),
                )
            else:
                cur.execute(
                    f"SELECT {SELECT_COLUMNS} FROM calendar_events "
                    "WHERE deleted = 0 AND start_at >= NOW() "
                    "ORDER BY start_at ASC LIMIT %s",
                    (limit,),
                )
            return cur.fetchall()
        finally:
            cur.close()
    finally:
        conn.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/events", response_model=EventsListResponse)
def get_events(
    limit: int = Query(default=10, ge=1, le=50),
    search: str | None = Query(default=None),
):
    try:
        rows = fetch_events(limit=limit, search=search)
    except Exception:
        log.exception("DB-Fehler bei /api/events")
        raise HTTPException(status_code=500, detail="Database error")

    events = [row_to_event(row) for row in rows]

    return EventsListResponse(
        events=events,
        count=len(events),
        query_time=datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        timezone=TIMEZONE_NAME,  # <--- Add this line
    )


@app.get("/api/events/{event_id}", response_model=EventResponse)
def get_event(event_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                f"SELECT {SELECT_COLUMNS} FROM calendar_events "
                "WHERE id = %s AND deleted = 0",
                (event_id,),
            )
            row = cur.fetchone()
        finally:
            cur.close()
    except Exception:
        log.exception("DB-Fehler bei /api/events/%d", event_id)
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Event not found")

    return row_to_event(row)


@app.get("/", response_class=HTMLResponse)
def index(
    search: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
):
    try:
        rows = fetch_events(limit=limit, search=search)
    except Exception:
        log.exception("DB-Fehler bei /")
        raise HTTPException(status_code=500, detail="Database error")

    events = []
    for row in rows:
        events.append({
            "id": row[0],
            "summary": row[1],
            "description": row[2],
            "location": row[3],
            "start_at": to_iso_local(row[4]) if row[4] else None,
            "end_at": to_iso_local(row[5]) if row[5] else None,
            "timezone": TIMEZONE_NAME,
            "all_day": bool(row[6]),
            "status": row[7],
        })

    return templates.TemplateResponse(
        "index.html",
        {"request": {}, "events": events, "search": search or ""},
    )
