-- Example queries against jobs.db (clean `jobs` table).
-- Run in DB Browser for SQLite, or: sqlite3 jobs.db < queries.sql
--
-- Timestamps are ISO-8601 UTC strings, so plain string comparison sorts
-- them correctly and date() extracts the day part.


-- 1. New postings from the most recent run.
--    first_seen equals the run timestamp of the run that first saw a
--    posting, so "new today" = first seen by the latest run.
SELECT company, title, department, location, url
FROM jobs
WHERE first_seen = (SELECT MAX(last_seen) FROM jobs)
ORDER BY company, title;


-- 2. Remote analyst roles (currently active).
--    A posting is active when the latest run saw it.
SELECT company, title, department, location, posted_at, url
FROM jobs
WHERE is_remote = 1
  AND title LIKE '%analyst%'
  AND last_seen = (SELECT MAX(last_seen) FROM jobs)
ORDER BY posted_at DESC;


-- 3. Postings per company over time (new postings by day first seen).
SELECT company,
       date(first_seen) AS day,
       COUNT(*)         AS new_postings
FROM jobs
GROUP BY company, day
ORDER BY day, company;


-- 4. Stale postings: seen on an earlier run but missing from the latest
--    one — the posting was likely closed or removed.
SELECT company, title, location, first_seen, last_seen
FROM jobs
WHERE last_seen < (SELECT MAX(last_seen) FROM jobs)
ORDER BY last_seen DESC, company;


-- 5. Current active posting count per company, with remote share.
SELECT company,
       COUNT(*)                                          AS active_postings,
       ROUND(100.0 * SUM(is_remote) / COUNT(*), 1)       AS pct_remote
FROM jobs
WHERE last_seen = (SELECT MAX(last_seen) FROM jobs)
GROUP BY company
ORDER BY active_postings DESC;
