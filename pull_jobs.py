"""Pull job postings from Greenhouse and Lever public job-board APIs into SQLite.

Reads companies.json, fetches every board, and upserts into jobs.db.
Safe to re-run daily: existing postings are updated in place, new ones
inserted, and postings that disappear from a board simply stop getting
their last_seen refreshed (that is how staleness is detected — see
queries.sql).

Run it with:  python pull_jobs.py
"""

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "jobs.db"
COMPANIES_PATH = PROJECT_ROOT / "companies.json"

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
LEVER_URL = "https://api.lever.co/v0/postings/{slug}?mode=json"

REQUEST_TIMEOUT = 30  # seconds
SLEEP_BETWEEN_COMPANIES = 2  # seconds; be polite to free, unauthenticated APIs


# --- database setup ---------------------------------------------------------

# Primary key on both tables is (source, source_job_id), not source_job_id
# alone: Greenhouse and Lever assign IDs independently, so a Greenhouse
# job 12345 and a Lever job 12345 would be different postings. Including
# source in the key keeps the namespaces separate, and the upsert below
# uses the same key so a daily re-run updates existing rows instead of
# duplicating them.
SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_jobs (
    source        TEXT NOT NULL,
    source_job_id TEXT NOT NULL,
    company       TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,   -- ISO-8601 UTC, when this JSON was last fetched
    raw_json      TEXT NOT NULL,   -- full posting as returned by the API
    PRIMARY KEY (source, source_job_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    source        TEXT NOT NULL,   -- 'greenhouse' or 'lever'
    source_job_id TEXT NOT NULL,
    company       TEXT NOT NULL,
    title         TEXT,
    department    TEXT,
    location      TEXT,
    is_remote     INTEGER,         -- 1 = remote, 0 = not remote
    posted_at     TEXT,            -- ISO-8601 UTC, when the posting was published
    updated_at    TEXT,            -- ISO-8601 UTC, last change reported by the source
    url           TEXT,
    first_seen    TEXT NOT NULL,   -- run timestamp of the first run that saw it
    last_seen     TEXT NOT NULL,   -- run timestamp of the latest run that saw it
    PRIMARY KEY (source, source_job_id)
);
"""


def utc_now_iso():
    """Current time as an ISO-8601 UTC string, e.g. 2026-08-04T19:00:00Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_utc_iso(ts):
    """Re-express an ISO-8601 timestamp as a UTC 'Z' string.

    Greenhouse reports timestamps in the board's local offset
    (e.g. 2026-08-04T20:33:43-04:00); storing everything in UTC keeps
    plain string comparison usable for ordering across companies.
    """
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return ts  # unrecognized format: keep the original rather than lose it
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- fetching ---------------------------------------------------------------

def fetch_board(source, slug):
    """Fetch all postings for one board.

    Returns (postings, error): a list of raw posting dicts on success,
    or an empty list plus an error string ('404' or a short message).
    """
    url = (GREENHOUSE_URL if source == "greenhouse" else LEVER_URL).format(slug=slug)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        return [], f"request failed: {exc}"
    if resp.status_code == 404:
        return [], "404"
    if resp.status_code != 200:
        return [], f"HTTP {resp.status_code}"
    try:
        data = resp.json()
    except ValueError:
        return [], "invalid JSON in response"
    # Greenhouse wraps the list in {"jobs": [...]}; Lever returns a bare list.
    if source == "greenhouse":
        postings = data.get("jobs", [])
    else:
        # Deleted Lever boards return 200 with {"ok": false, "error": "..."}
        # instead of a 404, so anything that isn't a list means no board.
        if not isinstance(data, list):
            return [], "404"
        postings = data
    return postings, None


# --- normalization ----------------------------------------------------------

def normalize_greenhouse(job, company):
    """Map one Greenhouse posting onto the clean-table columns.

    Greenhouse has no explicit remote flag, so remote is inferred from the
    location text ("Remote", "Remote - US", "Remote, EMEA" ...). That can
    miss postings that are remote but labeled with a city only.
    """
    location = (job.get("location") or {}).get("name") or None
    # departments is a list; boards in practice assign one, so take the first.
    departments = job.get("departments") or []
    department = departments[0].get("name") if departments else None
    return {
        "source_job_id": str(job["id"]),
        "company": company,
        "title": job.get("title"),
        "department": department,
        "location": location,
        "is_remote": 1 if location and "remote" in location.lower() else 0,
        "posted_at": to_utc_iso(job.get("first_published")),
        "updated_at": to_utc_iso(job.get("updated_at")),
        "url": job.get("absolute_url"),
    }


def normalize_lever(job, company):
    """Map one Lever posting onto the clean-table columns.

    Lever has an explicit workplaceType ('remote' / 'hybrid' / 'on-site' /
    'unspecified'). Only 'remote' counts as remote here; when the field is
    missing or 'unspecified' we fall back to the Greenhouse-style location
    text check.
    """
    categories = job.get("categories") or {}
    location = categories.get("location") or None
    workplace = job.get("workplaceType")
    if workplace in ("remote", "hybrid", "on-site", "onsite"):
        is_remote = 1 if workplace == "remote" else 0
    else:
        is_remote = 1 if location and "remote" in location.lower() else 0
    # createdAt is a millisecond epoch; Lever has no separate updated field.
    created_ms = job.get("createdAt")
    posted_at = (
        datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
        if created_ms
        else None
    )
    return {
        "source_job_id": str(job["id"]),
        "company": company,
        "title": job.get("text"),
        "department": categories.get("team"),
        "location": location,
        "is_remote": is_remote,
        "posted_at": posted_at,
        "updated_at": None,
        "url": job.get("hostedUrl"),
    }


# --- loading ----------------------------------------------------------------

UPSERT_JOB = """
INSERT INTO jobs (source, source_job_id, company, title, department, location,
                  is_remote, posted_at, updated_at, url, first_seen, last_seen)
VALUES (:source, :source_job_id, :company, :title, :department, :location,
        :is_remote, :posted_at, :updated_at, :url, :first_seen, :last_seen)
ON CONFLICT (source, source_job_id) DO UPDATE SET
    company    = excluded.company,
    title      = excluded.title,
    department = excluded.department,
    location   = excluded.location,
    is_remote  = excluded.is_remote,
    posted_at  = excluded.posted_at,
    updated_at = excluded.updated_at,
    url        = excluded.url,
    last_seen  = excluded.last_seen
    -- first_seen deliberately not updated: it marks the first run that saw
    -- the posting and must survive daily re-runs.
"""

UPSERT_RAW = """
INSERT INTO raw_jobs (source, source_job_id, company, fetched_at, raw_json)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (source, source_job_id) DO UPDATE SET
    company    = excluded.company,
    fetched_at = excluded.fetched_at,
    raw_json   = excluded.raw_json
"""


def load_company(conn, source, company, postings, run_ts):
    """Upsert one company's postings. Returns (new, updated, skipped) counts."""
    normalize = normalize_greenhouse if source == "greenhouse" else normalize_lever
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT source_job_id FROM jobs WHERE source = ? AND company = ?",
            (source, company),
        )
    }
    new = updated = skipped = 0
    for job in postings:
        try:
            clean = normalize(job, company)
        except (KeyError, TypeError, ValueError):
            skipped += 1  # malformed posting; don't let one bad record kill the run
            continue
        clean.update(source=source, first_seen=run_ts, last_seen=run_ts)
        conn.execute(UPSERT_JOB, clean)
        conn.execute(
            UPSERT_RAW,
            (source, clean["source_job_id"], company, run_ts, json.dumps(job)),
        )
        if clean["source_job_id"] in existing:
            updated += 1
        else:
            new += 1
    conn.commit()
    return new, updated, skipped


# --- main -------------------------------------------------------------------

def main():
    companies = json.loads(COMPANIES_PATH.read_text())
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    # One timestamp for the whole run so every row touched by this run gets
    # the same last_seen, which is what the staleness check compares against.
    run_ts = utc_now_iso()
    results = []
    not_found = []

    for i, entry in enumerate(companies):
        name, slug, source = entry["name"], entry["slug"], entry["source"]
        postings, error = fetch_board(source, slug)
        if error == "404":
            not_found.append(f"{slug} ({source})")
            print(f"{name}: board not found (404), skipping")
        elif error:
            print(f"{name}: {error}, skipping")
        else:
            new, updated, skipped = load_company(conn, source, name, postings, run_ts)
            results.append(
                {"company": name, "fetched": len(postings), "new": new,
                 "updated": updated, "skipped": skipped}
            )
            print(f"{name}: {len(postings)} fetched")
        if i < len(companies) - 1:
            time.sleep(SLEEP_BETWEEN_COMPANIES)

    conn.close()

    print(f"\nRun complete at {run_ts}")
    if results:
        print(pd.DataFrame(results).to_string(index=False))
    if not_found:
        print(f"\nSlugs that 404'd (fix or remove in companies.json): "
              f"{', '.join(not_found)}")


if __name__ == "__main__":
    main()
