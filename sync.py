#!/usr/bin/env python3
"""
Google Calendar (privater ICS-Feed) -> MariaDB Sync
Homelab: laeuft als Docker Container, pollt periodisch, expandiert RRULE/EXDATE/RECURRENCE-ID
und schreibt Einzel-Instanzen in eine eigene MariaDB-Datenbank (calendar_sync).
"""

import os
import sys
import time
import logging
import hashlib
from datetime import datetime, timedelta, timezone

import requests
import icalendar
import recurring_ical_events
import mysql.connector
from mysql.connector import Error as MySQLError

from api.database import get_connection

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("calendar-sync")

ICS_URL = os.environ["ICS_URL"]
DB_HOST = os.environ.get("DB_HOST", "mariadb.fritz.box")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_NAME = os.environ.get("DB_NAME", "calendar_sync")
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]

SYNC_INTERVAL_MINUTES = int(os.environ.get("SYNC_INTERVAL_MINUTES", "15"))
WINDOW_PAST_DAYS = int(os.environ.get("WINDOW_PAST_DAYS", "90"))
WINDOW_FUTURE_DAYS = int(os.environ.get("WINDOW_FUTURE_DAYS", "365"))
CALENDAR_LABEL = os.environ.get("CALENDAR_LABEL", "default")
HEALTHCHECK_URL = os.environ.get("HEALTHCHECK_URL", "")


DB_BOOTSTRAP = os.environ.get("DB_BOOTSTRAP", "false").lower() == "true"
DB_ROOT_USER = os.environ.get("DB_ROOT_USER")
DB_ROOT_PASSWORD = os.environ.get("DB_ROOT_PASSWORD")


def bootstrap_database():
    """Legt DB_NAME und DB_USER an, falls sie noch nicht existieren.
    Erfordert DB_ROOT_USER/DB_ROOT_PASSWORD mit ausreichenden Rechten
    (z.B. root auf dem MariaDB LXC). Wird nur ausgefuehrt, wenn
    DB_BOOTSTRAP=true gesetzt ist."""
    if not DB_BOOTSTRAP:
        return
    if not DB_ROOT_USER or not DB_ROOT_PASSWORD:
        log.warning("DB_BOOTSTRAP=true aber DB_ROOT_USER/DB_ROOT_PASSWORD fehlen, ueberspringe Bootstrap")
        return

    log.info("Bootstrap: pruefe/erstelle Datenbank '%s' und User '%s'", DB_NAME, DB_USER)
    root_conn = mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_ROOT_USER,
        password=DB_ROOT_PASSWORD,
        autocommit=True,
    )
    try:
        cur = root_conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4")
        cur.execute(
            "CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s",
            (DB_USER, DB_PASSWORD),
        )
        cur.execute(f"GRANT ALL PRIVILEGES ON `{DB_NAME}`.* TO %s@'%%'", (DB_USER,))
        cur.execute("FLUSH PRIVILEGES")
        cur.close()
        log.info("Bootstrap abgeschlossen")
    finally:
        root_conn.close()


def ensure_schema(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            calendar_label VARCHAR(64) NOT NULL,
            instance_key VARCHAR(255) NOT NULL,
            uid VARCHAR(255) NOT NULL,
            recurrence_id VARCHAR(64) NULL,
            summary VARCHAR(512),
            description TEXT,
            location VARCHAR(512),
            start_at DATETIME NOT NULL,
            end_at DATETIME NULL,
            all_day TINYINT(1) NOT NULL DEFAULT 0,
            status VARCHAR(32) DEFAULT 'CONFIRMED',
            deleted TINYINT(1) NOT NULL DEFAULT 0,
            last_seen_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_instance (calendar_label, instance_key),
            INDEX idx_start (start_at),
            INDEX idx_deleted (deleted)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    conn.commit()
    cur.close()


def fetch_ics(url: str) -> bytes:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content


def to_naive_utc(dt) -> datetime:
    """Normalisiert date/datetime auf ein naive UTC datetime fuer MySQL DATETIME."""
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    return datetime(dt.year, dt.month, dt.day)


def instance_key_for(event) -> tuple[str, str, str | None]:
    uid = str(event.get("UID", ""))
    recurrence_id = event.get("RECURRENCE-ID")
    rid_str = None
    if recurrence_id is not None:
        rid_dt = recurrence_id.dt
        rid_str = to_naive_utc(rid_dt).isoformat()
    key_source = uid + "|" + (rid_str or "")
    key = hashlib.sha1(key_source.encode("utf-8")).hexdigest()
    return key, uid, rid_str


def expand_events(ics_bytes: bytes, window_start: datetime, window_end: datetime):
    calendar = icalendar.Calendar.from_ical(ics_bytes)
    occurrences = recurring_ical_events.of(calendar).between(window_start, window_end)
    return occurrences


def upsert_event(cur, calendar_label, run_ts, event):
    key, uid, rid_str = instance_key_for(event)

    summary = str(event.get("SUMMARY", "") or "")
    description = str(event.get("DESCRIPTION", "") or "")
    location = str(event.get("LOCATION", "") or "")
    status = str(event.get("STATUS", "CONFIRMED") or "CONFIRMED")

    dtstart = event["DTSTART"].dt
    all_day = not isinstance(dtstart, datetime)
    start_at = to_naive_utc(dtstart)

    dtend_prop = event.get("DTEND")
    end_at = to_naive_utc(dtend_prop.dt) if dtend_prop else None

    cur.execute(
        """
        INSERT INTO calendar_events
            (calendar_label, instance_key, uid, recurrence_id, summary,
             description, location, start_at, end_at, all_day, status,
             deleted, last_seen_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)
        ON DUPLICATE KEY UPDATE
            summary = VALUES(summary),
            description = VALUES(description),
            location = VALUES(location),
            start_at = VALUES(start_at),
            end_at = VALUES(end_at),
            all_day = VALUES(all_day),
            status = VALUES(status),
            deleted = 0,
            last_seen_at = VALUES(last_seen_at)
        """,
        (
            calendar_label, key, uid, rid_str, summary, description,
            location, start_at, end_at, all_day, status, run_ts,
        ),
    )


def mark_missing_as_deleted(cur, calendar_label, run_ts, window_start, window_end):
    cur.execute(
        """
        UPDATE calendar_events
        SET deleted = 1
        WHERE calendar_label = %s
          AND deleted = 0
          AND last_seen_at < %s
          AND start_at BETWEEN %s AND %s
        """,
        (calendar_label, run_ts, window_start, window_end),
    )
    return cur.rowcount


def ping_healthcheck():
    if not HEALTHCHECK_URL:
        return
    try:
        resp = requests.get(HEALTHCHECK_URL, timeout=10)
        log.info("Healthcheck ping: %d", resp.status_code)
    except Exception:
        log.warning("Healthcheck ping fehlgeschlagen", exc_info=True)


def run_sync_once():
    run_ts = datetime.utcnow().replace(microsecond=0)
    window_start = run_ts - timedelta(days=WINDOW_PAST_DAYS)
    window_end = run_ts + timedelta(days=WINDOW_FUTURE_DAYS)

    log.info("Starte Sync fuer '%s' | Fenster %s bis %s", CALENDAR_LABEL, window_start, window_end)

    ics_bytes = fetch_ics(ICS_URL)
    occurrences = expand_events(ics_bytes, window_start, window_end)
    log.info("ICS geladen, %d Instanzen im Fenster gefunden", len(occurrences))

    conn = get_connection(autocommit=False)
    try:
        ensure_schema(conn)
        cur = conn.cursor()
        for occ in occurrences:
            upsert_event(cur, CALENDAR_LABEL, run_ts, occ)
        deleted_count = mark_missing_as_deleted(cur, CALENDAR_LABEL, run_ts, window_start, window_end)
        conn.commit()
        cur.close()
        log.info("Sync fertig. %d Events als geloescht markiert.", deleted_count)
        ping_healthcheck()
    except MySQLError:
        conn.rollback()
        log.exception("DB-Fehler beim Sync, Rollback ausgefuehrt")
        raise
    finally:
        conn.close()


def main():
    bootstrap_database()
    log.info(
        "calendar-sync gestartet | Intervall=%smin | Fenster=-%dd/+%dd",
        SYNC_INTERVAL_MINUTES, WINDOW_PAST_DAYS, WINDOW_FUTURE_DAYS,
    )
    while True:
        try:
            run_sync_once()
        except Exception:
            log.exception("Sync-Durchlauf fehlgeschlagen, versuche es beim naechsten Intervall erneut")
        time.sleep(SYNC_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
