"""Minimal Streamlit dashboard over jobs.db.

Run it with:  streamlit run app.py
"""

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parent / "jobs.db"

st.set_page_config(page_title="Job Pipeline", layout="wide")
st.title("Job postings")

if not DB_PATH.exists():
    st.error("jobs.db not found — run `python pull_jobs.py` first.")
    st.stop()


@st.cache_data
def load_jobs():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM jobs", conn)
    conn.close()
    return df


jobs = load_jobs()

# Only show postings the latest run still saw; anything older is stale
# (likely removed from the board).
latest_run = jobs["last_seen"].max()
active = jobs[jobs["last_seen"] == latest_run]

# --- filters ----------------------------------------------------------------
col1, col2, col3 = st.columns([2, 2, 1])
keyword = col1.text_input("Title contains", placeholder="e.g. analyst")
companies = col2.multiselect("Company", sorted(active["company"].unique()))
remote_only = col3.checkbox("Remote only")

filtered = active
if keyword:
    filtered = filtered[filtered["title"].str.contains(keyword, case=False, na=False)]
if companies:
    filtered = filtered[filtered["company"].isin(companies)]
if remote_only:
    filtered = filtered[filtered["is_remote"] == 1]

st.caption(
    f"{len(filtered)} of {len(active)} active postings "
    f"(latest run: {latest_run}; {len(jobs) - len(active)} stale postings hidden)"
)
st.dataframe(
    filtered[["company", "title", "department", "location", "is_remote",
              "posted_at", "first_seen", "url"]],
    use_container_width=True,
    hide_index=True,
    column_config={"url": st.column_config.LinkColumn("url")},
)

# --- chart: postings over time ----------------------------------------------
# posted_at is when the source says the job was published; postings without
# one (rare) are dropped from the chart only.
st.subheader("Postings over time")
by_month = (
    filtered.dropna(subset=["posted_at"])
    .assign(month=lambda d: d["posted_at"].str[:7])  # YYYY-MM from ISO string
    .groupby(["month", "company"])
    .size()
    .unstack(fill_value=0)
    .sort_index()
)
if by_month.empty:
    st.caption("No postings match the current filters.")
else:
    st.bar_chart(by_month)
