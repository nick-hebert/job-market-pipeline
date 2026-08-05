"""Export jobs.db to CSV files for Tableau (or any other BI tool).

Writes:
  exports/jobs_export.csv   - the full clean jobs table, one row per posting
  exports/daily_counts.csv  - per-company-per-month posting counts

Run it with:  python export_for_tableau.py
"""

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "jobs.db"
EXPORT_DIR = PROJECT_ROOT / "exports"


def main():
    EXPORT_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    jobs = pd.read_sql_query("SELECT * FROM jobs", conn)
    conn.close()

    jobs.to_csv(EXPORT_DIR / "jobs_export.csv", index=False)

    # Per-company-per-month counts, by the month the source says the posting
    # was published. Postings without a posted_at (rare) are excluded here
    # but still present in jobs_export.csv.
    counts = (
        jobs.dropna(subset=["posted_at"])
        .assign(month=lambda d: d["posted_at"].str[:7])  # YYYY-MM from ISO string
        .groupby(["company", "month"])
        .agg(postings=("source_job_id", "size"), remote_postings=("is_remote", "sum"))
        .reset_index()
        .sort_values(["company", "month"])
    )
    counts.to_csv(EXPORT_DIR / "daily_counts.csv", index=False)

    print(f"Wrote {len(jobs)} rows to exports/jobs_export.csv")
    print(f"Wrote {len(counts)} rows to exports/daily_counts.csv")


if __name__ == "__main__":
    main()
