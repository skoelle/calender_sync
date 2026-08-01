import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from api.database import get_connection

log = logging.getLogger("calendar-api")

app = FastAPI(title="Calendar Sync API")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

SELECT_COLUMNS = "id, summary, description, location, start_at, end_at, all_day, status"


class EventResponse(BaseModel):
    id: int
    summary: str | None
    description: str | None
    location: str | None
    start_at: str
    end_at: str | None
    all_day: bool
    status: str


class EventsListResponse(BaseModel):
    events: list[EventResponse]
    count: int
    query_time: str


def row_to_event(row) -> EventResponse:
    return EventResponse(
        id=row[0],
        summary=row[1],
        description=row[2],
        location=row[3],
        start_at=row[4].isoformat() if row[4] else None,
        end_at=row[5].isoformat() if row[5] else None,
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
        query_time=datetime.utcnow().isoformat() + "Z",
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
            "start_at": row[4],
            "end_at": row[5],
            "all_day": bool(row[6]),
            "status": row[7],
        })

    return templates.TemplateResponse(
        "index.html",
        {"request": {}, "events": events, "search": search or ""},
    )
