from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from api.database import get_connection

app = FastAPI(title="Calendar Sync API")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


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


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/events", response_model=EventsListResponse)
def get_events(
    limit: int = Query(default=10, ge=1, le=50),
    search: str | None = Query(default=None),
):
    conn = get_connection()
    cur = conn.cursor()

    if search:
        cur.execute(
            """
            SELECT id, summary, description, location, start_at, end_at, all_day, status
            FROM calendar_events
            WHERE deleted = 0 AND start_at >= NOW() AND summary LIKE %s
            ORDER BY start_at ASC
            LIMIT %s
            """,
            (f"%{search}%", limit),
        )
    else:
        cur.execute(
            """
            SELECT id, summary, description, location, start_at, end_at, all_day, status
            FROM calendar_events
            WHERE deleted = 0 AND start_at >= NOW()
            ORDER BY start_at ASC
            LIMIT %s
            """,
            (limit,),
        )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    events = [row_to_event(row) for row in rows]

    return EventsListResponse(
        events=events,
        count=len(events),
        query_time=datetime.utcnow().isoformat() + "Z",
    )


@app.get("/api/events/{event_id}", response_model=EventResponse)
def get_event(event_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, summary, description, location, start_at, end_at, all_day, status
        FROM calendar_events
        WHERE id = %s AND deleted = 0
        """,
        (event_id,),
    )

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Event not found")

    return row_to_event(row)


@app.get("/", response_class=HTMLResponse)
def index(
    search: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
):
    conn = get_connection()
    cur = conn.cursor()

    if search:
        cur.execute(
            """
            SELECT id, summary, description, location, start_at, end_at, all_day, status
            FROM calendar_events
            WHERE deleted = 0 AND start_at >= NOW() AND summary LIKE %s
            ORDER BY start_at ASC
            LIMIT %s
            """,
            (f"%{search}%", limit),
        )
    else:
        cur.execute(
            """
            SELECT id, summary, description, location, start_at, end_at, all_day, status
            FROM calendar_events
            WHERE deleted = 0 AND start_at >= NOW()
            ORDER BY start_at ASC
            LIMIT %s
            """,
            (limit,),
        )

    rows = cur.fetchall()
    cur.close()
    conn.close()

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
